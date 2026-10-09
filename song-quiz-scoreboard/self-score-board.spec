# -*- mode: python ; coding: utf-8 -*-
a=Analysis(['main.py'],pathex=[],binaries=[],datas=[],hiddenimports=['aiohttp'],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='self-score-board',debug=False,bootloader_ignore_signals=False,strip=False,upx=True,console=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,name='self-score-board')
