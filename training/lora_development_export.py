"""Export only this new study's bounded, stopped GPU evidence, never old runs."""
import hashlib
import io
import os
from pathlib import Path
import stat
import tarfile

from plugin.rhino_listener.c5_research_channel import read_json
from plugin.rhino_listener.c5_research_native import canonical, digest, require


def file_limit(package):
    if package.get('kind') == 'lora-common-final-comparison-v1':
        from plugin.rhino_listener.lora_development_runtime import configuration
        return configuration(package)['export_files_max']
    return 1024


def content_identity(value):
    return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
        'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read_stable(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and path.resolve() == path
            and before.st_size <= 32 * 1024 * 1024, 'bounded regular new evidence file required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        require(content_identity(os.fstat(stream.fileno())) == content_identity(before), 'evidence replaced before read')
        raw = stream.read(32 * 1024 * 1024 + 1)
        require(len(raw) == before.st_size and content_identity(os.fstat(stream.fileno())) == content_identity(before)
                and content_identity(path.lstat()) == content_identity(before), 'evidence changed during export')
    return raw


def export_gpu(state, package, stream):
    state = Path(state)
    settled = read_json(state, 'gpu-settlement.json')
    require(settled['package_sha256'] == digest(package) and settled['status'] == 'gpu_stopped',
            'do not snapshot uncertain live GPU evidence')
    files = []
    for name in ['gpu-started.claim.json', 'tasks-exposed.claim.json', 'gpu-settlement.json']:
        if (state / name).exists(): files.append(state / name)
    for index in (0, 1):
        attempt = state / ('load-%d' % index)
        if not attempt.exists(): continue
        require(attempt.resolve() == attempt, 'new attempt root must not alias another study')
        files.extend(attempt.glob('*.json'))
        if (attempt / 'worker.stderr').exists(): files.append(attempt / 'worker.stderr')
        peer = attempt / 'peer'
        if peer.exists():
            require(peer.resolve() == peer, 'peer directory alias refused')
            files.extend(peer.glob('*.json'))
    require(len(files) <= file_limit(package), 'bounded evidence population')
    records, total = {}, 0
    with tarfile.open(fileobj=stream, mode='w|') as archive:
        for path in sorted(files):
            raw = read_stable(path)
            total += len(raw)
            require(total <= 512 * 1024 * 1024, 'GPU evidence exceeds declared export budget')
            name = path.relative_to(state).as_posix()
            info = tarfile.TarInfo(name); info.size = len(raw); info.mode = 0o600
            archive.addfile(info, io.BytesIO(raw))
            records[name] = hashlib.sha256(raw).hexdigest()
        manifest = (canonical({'package_sha256': digest(package), 'files': records,
            'raw_bytes': total, 'new_study_only': True, 'cache_artifacts_excluded': True}) + '\n').encode()
        info = tarfile.TarInfo('export-manifest.json'); info.size = len(manifest); info.mode = 0o600
        archive.addfile(info, io.BytesIO(manifest))


def verify_archive(path, package):
    records, manifest, total = {}, None, 0
    with tarfile.open(path, 'r:') as archive:
        for item in archive:
            require(item.isfile() and item.size <= 32 * 1024 * 1024 and not item.name.startswith('/')
                    and '..' not in Path(item.name).parts and item.name not in records, 'unsafe or duplicate archive member')
            total += item.size
            require(total <= 513 * 1024 * 1024 and len(records) <= file_limit(package), 'bounded private export required')
            raw = archive.extractfile(item).read()
            if item.name == 'export-manifest.json':
                require(manifest is None, 'duplicate manifest')
                import json
                manifest = json.loads(raw)
            else: records[item.name] = hashlib.sha256(raw).hexdigest()
    require(manifest is not None and manifest['package_sha256'] == digest(package)
            and manifest['files'] == records, 'export manifest differs')
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
    return {'files': len(records), 'raw_bytes': manifest['raw_bytes'], 'archive_sha256': h.hexdigest(),
            'verified': True, 'package_sha256': digest(package)}
