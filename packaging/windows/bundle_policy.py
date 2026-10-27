"""Explicit Qt deployment scope; additions require a license/source review."""
from pathlib import PurePosixPath

QT_DLLS = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll'}
QT_PLUGINS = {
    'platforms/qwindows.dll', 'platforms/qoffscreen.dll', 'platforms/qminimal.dll',
    'styles/qmodernwindowsstyle.dll',
    'imageformats/qico.dll', 'imageformats/qjpeg.dll', 'imageformats/qgif.dll',
}
QT_MODULES = {'qtcore.pyd', 'qtgui.pyd', 'qtwidgets.pyd'}


def allowed(destination):
    path = str(destination).replace('\\', '/').lower()
    name = PurePosixPath(path).name
    if name.startswith('qt6') and name.endswith('.dll'):
        return name in QT_DLLS
    if 'pyside6/plugins/' in path:
        return path.split('pyside6/plugins/', 1)[1] in QT_PLUGINS
    if 'pyside6/' in path and name.endswith('.pyd'):
        return name in QT_MODULES
    if 'pyside6/translations/' in path or 'pyside6/qml/' in path:
        return False
    # Unused software OpenGL renderer and Qt's OpenSSL backend dependencies.
    return name not in {'opengl32sw.dll', 'libssl-3-x64.dll', 'libcrypto-3-x64.dll'}


def filter_entries(entries):
    return [entry for entry in entries if allowed(entry[0])]


def audit_bundle(bundle):
    files = [p for p in bundle.rglob('*') if p.is_file()]
    rejected = [str(p.relative_to(bundle)) for p in files if not allowed(p.relative_to(bundle))]
    if rejected:
        raise RuntimeError('Unreviewed Qt/runtime components: ' + ', '.join(rejected))
    names = {p.name.lower() for p in files}
    if not {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qwindows.dll'} <= names:
        raise RuntimeError('Required Windows Qt runtime is missing')
    return sorted(str(p.relative_to(bundle)).replace('\\', '/') for p in files)
