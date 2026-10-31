"""Metadata-only budget for this new run, never historical evidence cleanup."""
import os
from pathlib import Path
import stat
import shutil

from plugin.rhino_listener.c5_research_channel import private_directory
from plugin.rhino_listener.c5_research_native import require


def check_evidence_budget(root, config, *, cleanup=False, endpoint='mac'):
    root = Path(root)
    os.close(private_directory(root))
    if not cleanup:
        require(shutil.disk_usage(root).free >= config['minimum_free_bytes']//2,
                'physical cleanup reserve reached')
    count = total = 0
    require(endpoint in {'mac', 'gpu'}, 'explicit storage endpoint required')
    prefix = 'gpu_' if endpoint == 'gpu' else ''
    maximum = config[prefix+'evidence_total_bytes_max'] if cleanup else config[prefix+'evidence_work_bytes_max']
    file_max = config['evidence_files_max'] if cleanup else config['evidence_files_max']-64
    for directory, names, files in os.walk(root, followlinks=False):
        for name in names + files:
            p = Path(directory)/name
            try: item = p.lstat()
            except FileNotFoundError:
                # Atomic publishers remove their temporary link after promotion.
                # This is a conservative live size guard, not an identity audit.
                continue
            require(not stat.S_ISLNK(item.st_mode) and item.st_uid == os.getuid(), 'new evidence alias/ownership differs')
            if stat.S_ISREG(item.st_mode):
                # A publisher briefly owns two links. Count both conservatively
                # instead of turning normal publication into a spurious failure.
                count += 1; total += item.st_size
                require(count <= file_max and total <= maximum, 'bounded new evidence reserve reached')
            else: require(stat.S_ISDIR(item.st_mode), 'unexpected evidence device')
    return {'files': count, 'bytes': total, 'cleanup_reserve_bytes': config['evidence_cleanup_reserve_bytes'],
            'private_contents_read': False}
