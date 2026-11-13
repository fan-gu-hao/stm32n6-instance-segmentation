#!/usr/bin/env python3
"""封裝已建置通過的 STM32N6 UART 中斷版；加 --flash 才連線、核對與燒錄。

固定於 2026-09-14 05:57:33 建置的 ELF。沿用既有權重、命令資料與 FSBL。
先分離 .flash_section，避免直接使用跨位址空洞的大型 .bin。
燒錄前核對板上權重與命令；只寫入 0x70100000 的新應用程式並讀回比對。
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

PROJECT = 'STM32N6570-DK_GettingStarted_InstanceSegmentation'
ELF_SHA = '15e3e1369e5adc6716aec29deaa97d7a41488d7186a4dce8364d902dd7ef9f1e'
BASELINE_ELF_SHA = '8b56f5d914d15901e7abd9fe0ef7f8d576363a5dc6277e5075dc16149cca1b99'
PROBE_SN = '0051002A3234510137333934'
APP_ADDRESS = 0x70100000
WEIGHTS_ADDRESS = 0x70380000
EC_ADDRESS = 0x71380000
TOOLBIN = Path('/opt/st/stm32cubeide_2.2.0/plugins/'
               'com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.'
               '14.3.rel1.linux64_1.0.100.202602081740/tools/bin')
ST_BIN = Path('/usr/local/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin')


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_layout(section_table):
    lines = section_table.splitlines()
    sections = []
    for i, line in enumerate(lines[:-1]):
        match = re.match(r'\s*\d+\s+(\S+)\s+([0-9a-fA-F]+)\s+'
                         r'([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s', line)
        flags = {x.strip() for x in lines[i + 1].split(',')}
        if match and {'CONTENTS', 'ALLOC', 'LOAD'} <= flags:
            name, size, vma, lma = match.groups()
            if int(size, 16):
                sections.append((name, int(size, 16), int(vma, 16), int(lma, 16)))
    blobs = [x for x in sections if x[0] == '.flash_section']
    parts = [x for x in sections if x[0] != '.flash_section']
    require(len(blobs) == 1 and blobs[0][2] == EC_ADDRESS and blobs[0][3] == EC_ADDRESS
            and blobs[0][1] == 593920, '模型命令區段與目前固定模型不同。')
    require(parts, '找不到可封裝的應用程式區段。')
    require(all(0x34000400 <= vma and vma + size <= 0x34100000 and
                0x34000400 <= lma and lma + size <= 0x34100000
                for _, size, vma, lma in parts), '應用程式有超出 SRAM1 的載入區段。')
    low = min(x[3] for x in parts)
    high = max(x[3] + x[1] for x in parts)
    require(low == 0x34000400, '應用程式起始載入位址不同。')
    return high - low, blobs[0][1]


def check_signed(raw, signed):
    require(signed[:4] == b'STM2' and signed[1024:1024 + len(raw)] == raw,
            '開機標頭或簽章封裝中的應用程式內容不符。')
    require(len(signed) == ((1024 + len(raw) + 15) & ~15), '簽章封裝的大小或對齊不符。')
    require(APP_ADDRESS + len(signed) <= WEIGHTS_ADDRESS, '應用程式超過保留範圍。')


def check_readback(reference, actual, name):
    rounded_size = (len(reference) + 3) & ~3
    require(len(actual) == rounded_size and actual[:len(reference)] == reference,
            name + '讀回內容與參考檔不同。')


def deploy(repo, do_flash):
    app = repo / 'stm32ai-modelzoo-services/application_code/instance_segmentation/STM32N6'
    build = app / 'Application/STM32N6570-DK/STM32CubeIDE/ModelZoo'
    source = build / (PROJECT + '.elf')
    baseline = repo / 'results/region_event/deploy_20260913_184832_166479'
    objcopy = TOOLBIN / 'arm-none-eabi-objcopy'
    objdump = TOOLBIN / 'arm-none-eabi-objdump'
    signer = ST_BIN / 'STM32_SigningTool_CLI'
    programmer = ST_BIN / 'STM32_Programmer_CLI'
    loader = ST_BIN / 'ExternalLoader/MX66UW1G45G_STM32N6570-DK.stldr'
    paths = [source, baseline / 'app.elf', baseline / 'weights_reference.bin', objcopy, objdump, signer]
    if do_flash:
        paths += [programmer, loader]
    for path in paths:
        require(path.is_file(), '找不到既有檔案：' + str(path))
    elf_data = source.read_bytes()
    baseline_elf = (baseline / 'app.elf').read_bytes()
    weights_data = (baseline / 'weights_reference.bin').read_bytes()
    require(sha(elf_data) == ELF_SHA, '執行檔不是剛才零錯誤建置通過的 UART 中斷版本。')
    require(sha(baseline_elf) == BASELINE_ELF_SHA, '保存的區域事件基準執行檔已改變。')
    require(0 < len(weights_data) <= EC_ADDRESS - WEIGHTS_ADDRESS, '權重大小超出既有範圍。')
    for marker in (b'UART_TX_CONFIG,IT', b'PROFILE_IT_HEADER,', b'PROFILE_IT,', b'EVENT,'):
        require(marker in elf_data, '執行檔缺少版本標記：' + marker.decode())

    out = repo / 'results/uart_it' / datetime.now().strftime('deploy_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    print('本次封裝與燒錄紀錄：', out, flush=True)
    elf = out / 'app.elf'
    old_elf = out / 'baseline_app.elf'
    elf.write_bytes(elf_data)
    old_elf.write_bytes(baseline_elf)
    (out / 'weights_reference.bin').write_bytes(weights_data)
    shutil.copy2(Path(__file__), out / 'deploy_uart_it_v1.py')
    raw, ec, old_ec, signed = (out / name for name in
                             ('app_noecblob.bin', 'ecblob_reference.bin',
                              'baseline_ecblob.bin', 'app_signed.bin'))
    record = {'status': 'preparing', 'elf_sha256': ELF_SHA,
              'baseline_elf_sha256': BASELINE_ELF_SHA, 'stlink_serial': PROBE_SN,
              'application_address': hex(APP_ADDRESS), 'weights_address': hex(WEIGHTS_ADDRESS),
              'ecblob_address': hex(EC_ADDRESS), 'ecblob_section': '.flash_section',
              'model_readback_verified': False, 'application_write_started': False,
              'application_flash_verified': False, 'hardware_runtime_verified': False}
    manifest = out / 'manifest.json'

    def save():
        manifest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')

    def run(*arguments, quiet=False):
        command = [str(x) for x in arguments]
        print('$ ' + shlex.join(command), flush=True)
        with (out / 'deploy.log').open('a') as log:
            log.write('\n$ ' + shlex.join(command) + '\n')
            log.flush()
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, errors='replace')
            captured = []
            try:
                for line in process.stdout:
                    captured.append(line)
                    log.write(line)
                    log.flush()
                    if not quiet: print(line, end='', flush=True)
                status = process.wait()
            except BaseException:
                process.terminate()
                process.wait(timeout=30)
                raise
        require(status == 0, f'工具執行失敗，結束碼 {status}；請保留 {out / "deploy.log"}')
        return ''.join(captured)

    def readback(name, address, reference):
        output = out / (name + '_readback.bin')
        run(*connection, '--upload', hex(address), hex((len(reference) + 3) & ~3), output)
        data = output.read_bytes()
        check_readback(reference, data, name)
        print(name + '逐位元組核對通過。', flush=True)

    save()
    try:
        table = run(objdump, '-h', elf, quiet=True)
        (out / 'sections.txt').write_text(table)
        raw_size, ec_size = check_layout(table)
        run(objcopy, '-O', 'binary', '--remove-section=.flash_section', elf, raw)
        run(objcopy, '-O', 'binary', '--only-section=.flash_section', elf, ec)
        run(objcopy, '-O', 'binary', '--only-section=.flash_section', old_elf, old_ec)
        raw_data, ec_data = raw.read_bytes(), ec.read_bytes()
        require(len(raw_data) == raw_size and len(ec_data) == ec_size, '區段分離後的大小不符。')
        require(ec_data == old_ec.read_bytes(), '模型命令資料與已運作的區域事件版本不同。')
        print('模型命令與既有版本一致；封裝新的應用程式。', flush=True)
        run(signer, '-s', '-bin', raw, '-nk', '-of', '0x80000000',
            '-t', 'ssbl', '-hv', '2.3', '-align', '-o', signed)
        packed = signed.read_bytes()
        check_signed(raw_data, packed)
        record.update(status='packaged', application_size=len(packed), application_sha256=sha(packed),
                      weights_size=len(weights_data), weights_sha256=sha(weights_data),
                      ecblob_size=len(ec_data), ecblob_sha256=sha(ec_data))
        save()
        print(f'封裝完成：{len(packed)} 位元組；SHA-256：{sha(packed)}', flush=True)
        if not do_flash:
            print('尚未連線或燒錄。要更新板端，將 BOOT1 設為 H 並重設後，執行本腳本加 --flash。')
            return

        connection = (programmer, '-c', 'port=SWD', 'mode=HOTPLUG', 'sn=' + PROBE_SN, '-el', loader)
        readback('weights', WEIGHTS_ADDRESS, weights_data)
        readback('ecblob', EC_ADDRESS, ec_data)
        record.update(status='model_verified', model_readback_verified=True)
        save()
        require(signed.read_bytes() == packed, '燒錄前封裝檔內容已改變。')
        record.update(status='writing_application', application_write_started=True)
        save()
        run(*connection, '-w', signed, hex(APP_ADDRESS), '-v')
        readback('application', APP_ADDRESS, packed)
        record.update(status='application_verified', application_flash_verified=True)
        save()
        print('\n完成：UART 中斷版應用程式已燒錄並讀回核對。')
        print('請將 BOOT1 改回 L，開啟串列監看後按 RESET，進行實際執行驗證。')
        print('本次紀錄：', out)
    except BaseException as error:
        record.update(status='failed', error=str(error))
        save()
        print('本次步驟未完成，保留紀錄：', out, flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.home() / 'STM32N6ai/course14_yolov8n_seg_n6')
    parser.add_argument('--flash', action='store_true', help='核對指定 N6 板上的模型資料後，寫入並讀回應用程式')
    args = parser.parse_args()
    deploy(args.repo.expanduser().resolve(), args.flash)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit('停止：' + str(error))
