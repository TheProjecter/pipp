from distutils.core import setup
from Ft.Lib.DistExt import Py2Exe
import py2exe

setup(
    console = ['pipp.py'],
    windows = ['pippw.py', 'addtopath.py'],
    data_files = ['pipp-core.xsl', 'pipp.ico', 'pipp.xrc'],
    options = {'py2exe': {'packages':['pygments']}})
