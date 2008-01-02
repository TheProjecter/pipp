import wx, wx.xrc, sys, re, socket, os, threading, webbrowser, _winreg
from wx.xrc import XRCCTRL
import pipp

prog_dir = hasattr(sys, 'frozen') and sys.executable or sys.argv[0]
class Options(object):
    verbose = True
    path = os.path.join(os.path.dirname(prog_dir), 'example')
    port = 8080
    listen = '127.0.0.1'
options = Options()

class PippTaskBarIcon(wx.TaskBarIcon):
    def __init__(self, *args, **kwargs):
        super(PippTaskBarIcon, self).__init__(*args, **kwargs)
        self.SetIcon(wx.Icon('pipp.ico', wx.BITMAP_TYPE_ICO), 'Pipp')
        
    def CreatePopupMenu(self):
        menu = res.LoadMenu('popup_menu')
        global options
        if not options.path:
            for item in menu.GetMenuItems():
                if item.GetId() in (2, 3, 5):
                    item.Enable(False)
        wx.EVT_MENU(menu, 1, self.options)
        wx.EVT_MENU(menu, 2, self.browser)
        wx.EVT_MENU(menu, 3, self.rebuild)
        wx.EVT_MENU(menu, 4, self.exit)
        wx.EVT_MENU(menu, 5, self.explore)
        return menu

    def options(self, event):
        global panel
        panel.Show()
                
    def browser(self, event):
        webbrowser.open('http://%s:%d/index.html' % (options.listen, options.port))

    def rebuild(self, event):
        server.project.build_full()

    def exit(self, event):
        self.RemoveIcon()
        sys.exit()

    def explore(self, event):
        os.system('explorer ' + options.path)


def browse_folders(event):
    tb = XRCCTRL(panel, 'path')
    dlg = wx.DirDialog(panel)
    if tb.GetValue():
        dlg.SetPath(tb.GetValue())
    if dlg.ShowModal() == wx.ID_OK:
        tb.SetValue(dlg.GetPath())


def options_ok(event):
    
    # Validate
    msgs = []

    port = XRCCTRL(panel, 'port').GetValue().strip()    
    if re.match('^\d+$', port):
        port = int(port)
        if not 1 <= port <= 65535:
            msgs.append('The port must be a number 0-65535')
    else:        
        msgs.append('The port must be a number 0-65535')
    
    listen = XRCCTRL(panel, 'listen').GetValue().strip()
    if not re.match('^\d+\.\d+\.\d+\.\d+$', listen):
        msgs.append('The server address must be a valid ip address of an interface on this system')
    
    path = XRCCTRL(panel, 'path').GetValue().strip()
    if not all(os.path.exists(os.path.join(path, t)) for t in ('pipp.xsl', 'index.pip')):
        msgs.append('The path must point to a valid Pipp project (both pipp.xsl and index.pip must exist)')
    
    # Display any problems to the user
    if msgs:
        msg = wx.MessageDialog(panel, '\n'.join(msgs),
                             'Pipp', style = wx.OK | wx.ICON_EXCLAMATION)
        msg.ShowModal()
        return
        
    # Activate    
    global options
    options.port = port
    options.listen = listen
    options.path = path    

    _winreg.SetValueEx(regkey, 'Port', 0, _winreg.REG_SZ, str(port))
    _winreg.SetValueEx(regkey, 'Listen', 0, _winreg.REG_SZ, listen)
    _winreg.SetValueEx(regkey, 'Path', 0, _winreg.REG_SZ, path)
    
    global server
    server = PippServer(options)
    server.start()
        
    panel.Close()


class PippServer(threading.Thread):
    def __init__(self, options):
        super(PippServer, self).__init__()
        self.options = options
        
    def run(self):        
        self.project = pipp.PippProject(self.options.path, self.options)
        if self.project.new_project:
            self.project.build_full()
        self.project.serve((self.options.listen, self.options.port))
    

def options_cancel(event):
    panel.Close()


app = wx.PySimpleApp()
res = wx.xrc.EmptyXmlResource()
res.Load('pipp.xrc')

panel = res.LoadDialog(None, 'options')
wx.EVT_BUTTON(panel, 1, browse_folders)
wx.EVT_BUTTON(panel, 2, options_ok)
wx.EVT_BUTTON(panel, 3, options_cancel)

try:
    regkey = _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, 'Software\\Pajhome\\Pipp', 0, _winreg.KEY_ALL_ACCESS)
except WindowsError:
    regkey = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER, 'Software\\Pajhome\\Pipp')        
try:
    options.path,_ = _winreg.QueryValueEx(regkey, 'Path')
except WindowsError:
    pass
try:
    options.port,_ = _winreg.QueryValueEx(regkey, 'Port')
    options.port = int(options.port)
except WindowsError:
    pass
try:
    options.listen,_ = _winreg.QueryValueEx(regkey, 'Listen')
except WindowsError:
    pass
    
XRCCTRL(panel, 'path').SetValue(options.path)
XRCCTRL(panel, 'port').SetValue(str(options.port))
XRCCTRL(panel, 'listen').SetValue(options.listen)

server = PippServer(options)
server.start()

icon = PippTaskBarIcon()
app.MainLoop()
