$ErrorActionPreference = "Stop"
$root = "D:/Claude/reverseEngineering/Quartz"
$blender = "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
$userRes = "$root/tmp/blender_user"
New-Item -ItemType Directory -Force $userRes | Out-Null
$env:BLENDER_USER_RESOURCES = $userRes
$env:BLENDER_USER_CONFIG = "$userRes/config"
$env:BLENDER_USER_SCRIPTS = "$userRes/scripts"
$env:BLENDER_USER_EXTENSIONS = "$userRes/extensions"
$env:BLENDER_USER_DATAFILES = "$userRes/datafiles"
& $blender --background --factory-startup --python-exit-code 1 --python "$root/tools/dump_bpy_api.py"
exit $LASTEXITCODE
