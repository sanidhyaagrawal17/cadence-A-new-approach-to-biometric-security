@echo off
"d:\cadence reboot v2\venv311\Scripts\python.exe" - <<END
import google.protobuf as pb
print('module:', pb)
print('has runtime_version:', hasattr(pb, 'runtime_version'))
print('attrs sample:', [a for a in dir(pb) if 'runtime' in a or 'version' in a][:50])
END
