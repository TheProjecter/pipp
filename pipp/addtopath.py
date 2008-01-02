#--
# Adds the given directory to system path
# This is used by the Windows installer
#--
import sys
from _winreg import *

regenv = OpenKey(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 0, KEY_ALL_ACCESS)
oldpath, oldtype = QueryValueEx(regenv, 'Path')

progdir = sys.argv[1]
if progdir not in oldpath:
    newpath = '%s;%s' % (oldpath, progdir)
    SetValueEx(regenv, 'Path', 0, oldtype, newpath)
