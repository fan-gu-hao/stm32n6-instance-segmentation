#!/usr/bin/env python3
"""還原第一次 UART 中斷修改之前的區域事件＋A3 版本。

預設核對備份；--restore 還原本機來源，--restore --flash 同時燒回已保存的舊韌體。
不重建、不重新簽章、不執行 Git 操作。使用兩次安裝紀錄的最早備份還原來源。
目前檔案與中斷版建置目錄先封存；新增加的檔案移出有效原始碼目錄。
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

APP_REL = Path('stm32ai-modelzoo-services/application_code/instance_segmentation/STM32N6')
BOARD_REL = APP_REL / 'Application/STM32N6570-DK'
INSTALLS = ('install_20260914_054405_207092', 'install_20260914_055728_067784')
BASELINE = 'results/region_event/deploy_20260913_184832_166479'
SIGNED_SHA = '6ab43d7adadc9b57bd3de5cb531591dfb139c2322cba4ed2d83896361b66491f'
ELF_SHA = '8b56f5d914d15901e7abd9fe0ef7f8d576363a5dc6277e5075dc16149cca1b99'
PROGRAMMER = Path('/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI')
LOADER = PROGRAMMER.parent / 'ExternalLoader/MX66UW1G45G_STM32N6570-DK.stldr'
PROBE = '0051002A3234510137333934'


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, path.stat().st_mode & 0o777 if path.exists() else 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def plan_restore(repo):
    main = BOARD_REL / 'Src/main.c'
    project = BOARD_REL / 'STM32CubeIDE/.project'
    source = BOARD_REL / 'Src/project_uart_it.c'
    header = BOARD_REL / 'Inc/project_uart_it.h'
    installer = Path('scripts/install_uart_it_v1.py')
    required = {main, project, source, header, installer}
    allowed = required | {BOARD_REL / 'Inc/stm32n6xx_hal_conf.h'}
    desired, evidence = {}, []
    for folder in INSTALLS:
        root = repo / 'results/uart_it' / folder
        manifest = root / 'manifest.json'
        require(manifest.is_file(), '找不到已記錄的安裝備份：' + str(manifest))
        record = json.loads(manifest.read_text())
        require(record.get('status') == 'applied', '安裝備份狀態不符：' + str(manifest))
        evidence.append(manifest)
        for item in record['files']:
            relative = Path(item['path'])
            require(relative in allowed, '安裝紀錄含非本次修改的路徑：' + str(relative))
            if relative in desired:
                continue
            digest = item['before_sha256']
            if digest is None:
                desired[relative] = None
            else:
                backup = root / 'before' / relative
                data = backup.read_bytes()
                require(sha(data) == digest, '修改前備份校驗失敗：' + str(backup))
                desired[relative] = data
    require(required <= desired.keys(), '安裝紀錄缺少必要的還原項目。')
    require(desired[source] is None and desired[header] is None,
            '串列模組並非本次新增，不能按目前方式撤回。')
    previous_main = desired[main]
    previous_project = desired[project]
    require(previous_main is not None and previous_project is not None, '缺少原始主程式或 IDE 設定。')
    require(all(marker in previous_main for marker in
                (b'PROJECT_A3_PROFILE_V1', b'project_region_event.h', b'PROFILE_HEADER,',
                 b'UART_SendInferenceResult', b'HAL_UART_Transmit(')),
            '備份不是區域事件＋A3 的原始串列版本。')
    require(b'ProjectUart_' not in previous_main and b'project_uart_it.c' not in previous_project,
            '備份仍含本次串列中斷修改。')
    for relative in desired:
        path = repo / relative
        require(not path.is_symlink() and (not path.exists() or path.is_file()),
                '還原路徑不是一般檔案：' + str(path))
    signed = (repo / BASELINE / 'app_signed.bin').read_bytes()
    elf = (repo / BASELINE / 'app.elf').read_bytes()
    require(sha(signed) == SIGNED_SHA and len(signed) == 448992,
            '保存的舊韌體映像大小或 SHA-256 不符。')
    require(sha(elf) == ELF_SHA, '保存的舊執行檔 SHA-256 不符。')
    require(signed[:4] == b'STM2', '舊韌體的開機標頭不符。')
    return desired, evidence, signed


def restore(repo, apply, flash):
    desired, evidence, signed_data = plan_restore(repo)
    if flash:
        require(apply, '燒錄還原請使用 --restore --flash。')
        for path in (PROGRAMMER, LOADER): require(path.is_file(), '找不到工具：' + str(path))
    print('已核對還原點：區域事件＋A3，第一次串列中斷修改之前。')
    print('舊韌體：448992 位元組；SHA-256：' + SIGNED_SHA)
    for relative, data in desired.items():
        print(('恢復備份：' if data is not None else '封存並移出：') + str(relative))
    if not apply:
        print('核對完成；執行還原與燒錄請加 --restore --flash。')
        return

    out = repo / 'results/uart_it' / datetime.now().strftime('rollback_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    print('目前修改的封存位置：', out, flush=True)
    shutil.copy2(Path(__file__), out / 'restore_before_uart_it.py')
    for i, path in enumerate(evidence):
        shutil.copy2(path, out / f'install_manifest_{i}.json')
    image = out / 'restored_app_signed.bin'
    image.write_bytes(signed_data)
    previous = {}
    records = []
    # 在任何來源檔變更之前，先保存所有目前內容。
    for relative, data in desired.items():
        path = repo / relative
        before = path.read_bytes() if path.exists() else None
        previous[relative] = before
        if before is not None:
            backup = out / 'before' / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            require(backup.read_bytes() == before, '封存目前檔案時校驗失敗：' + str(path))
        records.append({'path': str(relative), 'before_sha256': sha(before) if before is not None else None,
                        'restored_sha256': sha(data) if data is not None else None})
    state = {'status': 'prepared', 'files': records, 'sources_restored': False,
             'application_address': '0x70100000', 'application_sha256': SIGNED_SHA,
             'application_write_started': False, 'application_readback_verified': False,
             'hardware_runtime_verified': False}
    manifest = out / 'manifest.json'

    def save():
        atomic_write(manifest, (json.dumps(state, indent=2, ensure_ascii=False) + '\n').encode())

    build = repo / BOARD_REL / 'STM32CubeIDE/ModelZoo'
    archived_build = out / 'interrupt_build_ModelZoo'
    changed = []
    save()
    try:
        if build.exists():
            require(build.is_dir() and not build.is_symlink(), '建置目錄不是預期的一般目錄。')
            build.rename(archived_build)
            state['archived_build'] = str(archived_build)
        for relative, data in desired.items():
            path = repo / relative
            actual = path.read_bytes() if path.exists() else None
            require(actual == previous[relative], '還原期間檔案被其他程式修改：' + str(path))
            if data is None:
                if path.exists(): path.unlink()
            else:
                atomic_write(path, data)
            changed.append(relative)
        for relative, data in desired.items():
            path = repo / relative
            require((path.read_bytes() if path.exists() else None) == data,
                    '還原後內容不符：' + str(path))
    except BaseException:
        for relative in reversed(changed):
            path = repo / relative
            current = path.read_bytes() if path.exists() else None
            if current == desired[relative]:
                if previous[relative] is None:
                    if path.exists(): path.unlink()
                else:
                    atomic_write(path, previous[relative])
        if archived_build.exists() and not build.exists(): archived_build.rename(build)
        state['status'] = 'source_restore_failed'
        save()
        raise
    state.update(status='sources_restored', sources_restored=True)
    save()
    print('原始碼與 IDE 設定已恢復；中斷版建置產物已封存。', flush=True)
    if not flash:
        print('本次僅恢復本機來源，尚未燒回舊韌體。')
        return

    def run(*args):
        command = [str(x) for x in args]
        print('$ ' + shlex.join(command), flush=True)
        with (out / 'flash.log').open('a') as log:
            log.write('\n$ ' + shlex.join(command) + '\n')
            log.flush()
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, errors='replace')
            try:
                for line in process.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
                    log.flush()
                status = process.wait()
            except BaseException:
                process.terminate()
                process.wait(timeout=30)
                raise
        require(status == 0, f'燒錄工具結束碼 {status}，請保留 {out / "flash.log"}')

    connection = (PROGRAMMER, '-c', 'port=SWD', 'mode=HOTPLUG', 'sn=' + PROBE, '-el', LOADER)
    try:
        require(image.read_bytes() == signed_data, '寫入前舊韌體封裝內容已改變。')
        state.update(status='writing_baseline', application_write_started=True)
        save()
        run(*connection, '-w', image, '0x70100000', '-v')
        readback = out / 'application_readback.bin'
        run(*connection, '--upload', '0x70100000', hex(len(signed_data)), readback)
        require(readback.read_bytes() == signed_data, '燒回後的逐位元組核對失敗。')
        state.update(status='baseline_restored', application_readback_verified=True)
        save()
    except BaseException as error:
        state.update(status='firmware_restore_failed', error=str(error))
        save()
        print('本機來源已恢復，但舊韌體燒回尚未確認成功；紀錄：', out, flush=True)
        raise
    print('\n完成：原始碼已還原，舊韌體已燒回並逐位元組核對通過。')
    print('請將 BOOT1 切回 L，按 RESET，確認螢幕與原本的區域事件恢復。')
    print('還原紀錄與撤回修改的封存：', out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home() / 'STM32N6ai/course14_yolov8n_seg_n6')
    parser.add_argument('--restore', action='store_true', help='封存目前修改並恢復原始碼')
    parser.add_argument('--flash', action='store_true', help='將已保存的舊應用程式燒回指定 N6 板')
    args = parser.parse_args()
    restore(args.repo.expanduser().resolve(), args.restore, args.flash)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        raise SystemExit('停止：' + str(error))
