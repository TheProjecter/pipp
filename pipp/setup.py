from distutils.core import setup
from Ft.Lib.DistExt import Py2Exe
import py2exe

setup(console=['pipp.py', 'addtopath.py'], options={'py2exe': {'packages':['pygments']}})
