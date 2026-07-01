"""
keyring_enum: credential *enumeration* on top of python-keyring.

python-keyring (https://github.com/jaraco/keyring) only does point lookups by
(service, username); none of its backends expose a way to *list* what is
stored. This module adds that, without modifying the installed ``keyring``
package, by dispatching on the active backend type and talking to each
platform's underlying secret store directly.

Design choices:

* **Identifiers only.** Enumeration yields ``(service, username)`` and never
  reads/decrypts secret material. That makes it safe for auditing/listing and
  avoids per-item unlock prompts.
* **Standalone.** No monkeypatching, no subclassing keyring's classes. You call
  :func:`list_credentials` instead of a (nonexistent) ``keyring`` function.
* **Graceful degradation.** A backend that genuinely can't enumerate raises
  :class:`EnumerationNotSupported`; everything else returns an iterator.

Usage::

    import keyring_enum
    for service, username in keyring_enum.list_credentials():
        print(service, username)

    # or for an explicit backend
    import keyring
    keyring_enum.list_credentials(keyring.get_keyring())
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from keyring.backend import KeyringBackend

# The internal helpers and per-backend enumerators operate *structurally* (they
# read ``.backends``, ``type(x)``, scheme dicts, etc.) and are also handed
# chainer objects that are not ``KeyringBackend`` subclasses. ``Backend`` marks
# those duck-typed parameters; the public API stays typed as ``KeyringBackend``.
Backend = typing.Any


class EnumerationNotSupported(NotImplementedError):
    """Raised when the active backend has no way to enumerate credentials."""


class Credential(typing.NamedTuple):  # pylint: disable=missing-class-docstring
    """A (service, username) identifier pair from the keyring."""

    service: str | None
    username: str | None


def list_credentials(
    backend: KeyringBackend | None = None,
) -> typing.Iterator[Credential]:
    """
    Enumerate ``(service, username)`` pairs in the given keyring *backend*.

    If *backend* is None, the active keyring (``keyring.get_keyring()``) is
    used. Raises :class:`EnumerationNotSupported` if the backend type is not
    enumerable by this module.
    """
    if backend is None:
        import keyring  # pylint: disable=import-outside-toplevel

        backend = keyring.get_keyring()

    # Resolve through a chainer to its first enumerable backend.
    for candidate in _unwrap(backend):
        impl = _dispatch(candidate)
        if impl is not None:
            yield from impl(candidate)
            return

    raise EnumerationNotSupported(f"No enumerable backend found for {type(backend).__name__!r}")


def _unwrap(backend: Backend) -> typing.Iterator[Backend]:
    """Yield backend, expanding a ChainerBackend into its members."""
    # Avoid importing the chainer module (it may not be importable on all
    # platforms); detect duck-typed by the 'backends' attribute it exposes.
    inner = getattr(backend, "backends", None)
    if inner:
        for member in inner:
            yield from _unwrap(member)
    else:
        yield backend


def _qualname(backend: Backend) -> str:
    """Return the ``module.ClassName`` of a backend instance."""
    return f"{type(backend).__module__}.{type(backend).__name__}"


def _dispatch(
    backend: Backend,
) -> typing.Callable[[Backend], typing.Iterator[Credential]] | None:
    """Return the enumerator function for this backend, or None."""
    # Match on module+class name rather than isinstance so we never have to
    # import a backend whose deps aren't installed on this platform.
    return _ENUMERATORS.get(_qualname(backend))


# --------------------------------------------------------------------------- #
# Windows: Credential Manager via win32cred.CredEnumerate
# --------------------------------------------------------------------------- #
def _enumerate_windows(_backend: Backend) -> typing.Iterator[Credential]:
    try:
        from win32ctypes.pywin32 import win32cred  # pylint: disable=import-outside-toplevel  # pywin32-ctypes
    except ImportError:
        import win32cred  # pylint: disable=import-outside-toplevel  # pywin32  # pyrefly: ignore[missing-source-for-stubs]  # ty: ignore[unresolved-import]

    # Filter=None, Flags=0 -> all of the current user's credentials.
    raw_creds = win32cred.CredEnumerate(None, 0) or []
    for raw_cred in raw_creds:
        target = raw_cred.get("TargetName")
        username = raw_cred.get("UserName") or None
        service = target
        # keyring stores colliding entries under a compound target
        # "{username}@{service}"; undo that so callers see the real service.
        if username and target and target.startswith(f"{username}@"):
            service = target[len(username) + 1 :]
        yield Credential(service, username)


# --------------------------------------------------------------------------- #
# Linux: Secret Service via secretstorage
# --------------------------------------------------------------------------- #
def _enumerate_secretservice(
    backend: Backend,
) -> typing.Iterator[Credential]:
    from contextlib import closing  # pylint: disable=import-outside-toplevel

    scheme = backend.schemes[backend.scheme]
    collection = backend.get_preferred_collection()
    with closing(collection.connection):
        for item in collection.get_all_items():
            attrs = item.get_attributes()  # no get_secret() -> no secret read
            yield Credential(
                attrs.get(scheme["service"]),
                attrs.get(scheme["username"]),
            )


# --------------------------------------------------------------------------- #
# Linux: libsecret via gi/Secret
# --------------------------------------------------------------------------- #
def _enumerate_libsecret(backend: Backend) -> typing.Iterator[Credential]:
    from gi.repository import Secret  # pylint: disable=import-outside-toplevel  # ty: ignore[unresolved-import]

    scheme = backend.schemes[backend.scheme]
    # Empty attribute dict + ALL matches every item for this schema.
    # No LOAD_SECRETS flag -> secrets are not retrieved.
    items = Secret.password_search_sync(
        backend.schema,
        {},
        Secret.SearchFlags.ALL,
        None,
    )
    for item in items:
        attrs = item.get_attributes()
        yield Credential(
            attrs.get(scheme["service"]),
            attrs.get(scheme["username"]),
        )


# --------------------------------------------------------------------------- #
# macOS: Keychain via the Security framework (ctypes), the way keyring itself
# integrates. We reuse keyring's own bindings (api._sec, api.create_query,
# api.k_, api.cfstr_to_str, api.Error) and add only the symbols keyring's
# single-item path doesn't bind: kSecMatchLimitAll, kSecReturnAttributes, and
# the CFArray/CFDictionary getters needed to unpack a multi-item result.
#
# We request kSecReturnAttributes (not kSecReturnData), so no secret material
# is read and no per-item auth prompt is triggered.
# --------------------------------------------------------------------------- #
def _enumerate_macos(_backend: Backend) -> typing.Iterator[Credential]:
    import ctypes  # pylint: disable=import-outside-toplevel
    import ctypes.util  # pylint: disable=import-outside-toplevel

    from keyring.backends.macOS import api  # pylint: disable=import-outside-toplevel

    sec = api._sec  # pylint: disable=protected-access
    # Core Foundation lives in the same process; load it for the array/dict
    # accessors keyring doesn't expose.
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))

    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    query = api.create_query(
        kSecClass=api.k_("kSecClassGenericPassword"),
        kSecMatchLimit=api.k_("kSecMatchLimitAll"),
        kSecReturnAttributes=True,
    )

    result = ctypes.c_void_p()
    status = sec.SecItemCopyMatching(query, ctypes.byref(result))
    if status == api.error.item_not_found:
        return
    api.Error.raise_for_status(status)
    if not result.value:
        return

    svce = api.k_("kSecAttrService")
    acct = api.k_("kSecAttrAccount")
    count = cf.CFArrayGetCount(result)
    for i in range(count):
        item = cf.CFArrayGetValueAtIndex(result, i)
        yield Credential(
            _cf_attr_to_str(cf, item, svce),
            _cf_attr_to_str(cf, item, acct),
        )


def _cf_attr_to_str(cf: typing.Any, item: typing.Any, key: typing.Any) -> str | None:
    """Read a CFString attribute from a result dict as a Python str, or None.

    Keychain attribute values come back as CFStrings; keyring's
    ``cfstr_to_str`` decodes CFData, so we read the CFString bytes directly.
    """
    import ctypes  # pylint: disable=import-outside-toplevel

    value = cf.CFDictionaryGetValue(item, key)
    if not value:
        return None
    cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
    cf.CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k_cf_string_encoding_utf8 = 0x08000100
    ptr = cf.CFStringGetCStringPtr(value, k_cf_string_encoding_utf8)
    if ptr:
        decoded: str = ptr.decode("utf-8", "replace")
        return decoded
    # Fast pointer path unavailable; fall back to a copied buffer.
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    buf = ctypes.create_string_buffer(4096)
    if cf.CFStringGetCString(value, buf, len(buf), k_cf_string_encoding_utf8):
        return buf.value.decode("utf-8", "replace")
    return None


_ENUMERATORS: dict[str, typing.Callable[[Backend], typing.Iterator[Credential]]] = {
    "keyring.backends.Windows.WinVaultKeyring": _enumerate_windows,
    "keyring.backends.SecretService.Keyring": _enumerate_secretservice,
    "keyring.backends.libsecret.Keyring": _enumerate_libsecret,
    "keyring.backends.macOS.Keyring": _enumerate_macos,
}


if __name__ == "__main__":
    for cred in list_credentials():
        print(f"{cred.service!r}\t{cred.username!r}")
