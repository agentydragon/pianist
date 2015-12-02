#!/usr/bin/python
#
# Copyright 2010 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Keyboard Status Monitor.
Monitors one or more keyboards and mouses.
Shows their status graphically.
"""

__author__ = 'Scott Kirkwood (scott+keymon@forusers.com)'
__version__ = '1.17'

import locale
import logging
import pygtk
pygtk.require('2.0')
import gettext
import gobject
import gtk
import os
import sys
import time
try:
  import xlib
except ImportError:
  print 'Error: Missing xlib, run sudo apt-get install python-xlib'
  sys.exit(-1)

import options
import mod_mapper
import settings
import shaped_window

from ConfigParser import SafeConfigParser

gettext.install('key-mon', 'locale')

class KeyMon:
  """main KeyMon window class."""

  def __init__(self, options):
    """Create the Key Mon window.
    Options dict:
      meta: boolean show the meta (windows key)
      kbd_file: string Use the kbd file given.
      theme: Name of the theme to use to draw keys
    """
    self.btns = ['MOUSE', 'BTN_RIGHT', 'BTN_MIDDLE', 'BTN_MIDDLERIGHT',
                 'BTN_LEFT', 'BTN_LEFTRIGHT', 'BTN_LEFTMIDDLE',
                 'BTN_LEFTMIDDLERIGHT']
    self.options = options
    self.pathname = os.path.dirname(os.path.abspath(__file__))
    # Make lint happy by defining these.
    self.hbox = None
    self.window = None
    self.event_box = None
    self.mouse_indicator_win = None

    self.move_dragged = False
    self.shape_mask_current = None
    self.shape_mask_cache = {}

    self.MODS = ['SHIFT', 'CTRL', 'META', 'ALT']


    self.options.kbd_files = settings.get_kbd_files()
    self.modmap = mod_mapper.safely_read_mod_map(self.options.kbd_file, self.options.kbd_files)

    self.devices = xlib.XEvents()
    self.devices.start()

    self.create_window()

    path = '/tmp/prvak-log-%s' % time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    self.event_log = open(path, 'w')

  def get_option(self, attr):
    """Shorthand for getattr(self.options, attr)"""
    return getattr(self.options, attr)

  def create_window(self):
    """Create the main window."""
    self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    self.window.set_resizable(False)

    self.window.set_title('Keyboard Status Monitor')
    width, height = 30, 48
    self.window.set_default_size(int(width), int(height))
    self.window.set_decorated(True)

    self.mouse_indicator_win = shaped_window.ShapedWindow(
        self.svg_name('mouse-indicator'),
        timeout=self.options.visible_click_timeout)

    self.window.set_opacity(self.options.opacity)
    self.window.set_keep_above(True)

    self.event_box = gtk.EventBox()
    self.window.add(self.event_box)
    self.event_box.show()

    self.hbox = gtk.HBox(False, 0)
    self.event_box.add(self.hbox)

    self.layout_boxes()
    self.hbox.show()

    self.add_events()

    self.set_accept_focus(False)
    self.window.set_skip_taskbar_hint(True)

    old_x = self.options.x_pos
    old_y = self.options.y_pos
    if old_x != -1 and old_y != -1 and old_x and old_y:
      self.window.move(old_x, old_y)
    self.window.show()

  def layout_boxes(self):
    for child in self.hbox.get_children():
      self.hbox.remove(child)

  def svg_name(self, fname):
    """Return an svg filename given the theme, system."""
    themepath = self.options.themes[self.options.theme][1]
    return os.path.join(themepath, '%s.svg' % (fname))

  def add_events(self):
    """Add events for the window to listen to."""
    self.window.connect('destroy', self.destroy)
    self.window.connect('button-press-event', self.button_pressed)
    self.window.connect('button-release-event', self.button_released)
    self.window.connect('leave-notify-event', self.pointer_leave)

    accelgroup = gtk.AccelGroup()
    key, modifier = gtk.accelerator_parse('<Control>q')
    accelgroup.connect_group(key, modifier, gtk.ACCEL_VISIBLE, self.quit_program)

    gobject.idle_add(self.on_idle)

  def button_released(self, unused_widget, evt):
    """A mouse button was released."""
    if evt.button == 1:
      self.move_dragged = None
    return True

  def button_pressed(self, widget, evt):
    """A mouse button was pressed."""
    self.set_accept_focus(True)
    if evt.button == 1:
      self.move_dragged = widget.get_pointer()
      self.window.set_opacity(self.options.opacity)
    return True

  def pointer_leave(self, unused_widget, unused_evt):

    self.set_accept_focus(False)

  def set_accept_focus(self, accept_focus=True):

    self.window.set_accept_focus(accept_focus)
    if accept_focus:
      logging.debug('window now accepts focus')
    else:
      logging.debug('window now does not accept focus')

  def _window_moved(self):
    """The window has moved position, save it."""
    if not self.move_dragged:
      return
    old_p = self.move_dragged
    new_p = self.window.get_pointer()
    x, y = self.window.get_position()
    x, y = x + new_p[0] - old_p[0], y + new_p[1] - old_p[1]
    self.window.move(x, y)

    logging.info('Moved window to %d, %d' % (x, y))
    self.options.x_pos = x
    self.options.y_pos = y

  def on_idle(self):
    """Check for events on idle."""
    event = self.devices.next_event()
    try:
      if event:
        self.handle_event(event)
      time.sleep(0.001)
    except KeyboardInterrupt:
      self.quit_program()
      return False
    return True  # continue calling

  def _log_event(self, event):
    self.event_log.write('%.5f;%s;%s;%s\n' % (
        time.time(), event.type, event.code, event.value))
    self.event_log.flush()

  def handle_event(self, event):
    """Handle an X event."""

    self._log_event(event)

  def quit_program(self, *unused_args):
    """Quit the program."""
    self.devices.stop_listening()
    self.destroy(None)

  def destroy(self, unused_widget, unused_data=None):
    """Also quit the program."""
    self.devices.stop_listening()
    self.options.save()
    gtk.main_quit()

def create_options():
  opts = options.Options()

  opts.add_option(opt_long='--visible-click-timeout', dest='visible_click_timeout',
                  type='float', default=0.2,
                  ini_group='ui', ini_name='visible_click_timeout',
                  help=_('Timeout before highly visible click disappears. '
                         'Defaults to %default'))
  opts.add_option(opt_long='--only_combo', dest='only_combo', type='bool',
                  ini_group='ui', ini_name='only_combo',
                  default=False,
                  help=_('Show only key combos (ex. Control-A)'))
  opts.add_option(opt_long='--sticky', dest='sticky_mode', type='bool',
                  ini_group='ui', ini_name='sticky_mode',
                  default=False,
                  help=_('Sticky mode'))
  opts.add_option(opt_long='--visible_click', dest='visible_click', type='bool',
                  ini_group='ui', ini_name='visible-click',
                  default=False,
                  help=_('Show where you clicked'))
  opts.add_option(opt_long='--kbdfile', dest='kbd_file',
                  ini_group='devices', ini_name='map',
                  default=None,
                  help=_('Use this kbd filename.'))
  opts.add_option(opt_short='-t', opt_long='--theme', dest='theme', type='str',
                  ini_group='ui', ini_name='theme', default='classic',
                  help=_('The theme to use when drawing status images (ex. "-t apple").'))
  opts.add_option(opt_long='--reset', dest='reset', type='bool',
                  help=_('Reset all options to their defaults.'),
                  default=None)

  opts.add_option(opt_short=None, opt_long='--opacity', type='float',
                  dest='opacity', default=1.0, help='Opacity of window',
                  ini_group='ui', ini_name='opacity')
  opts.add_option(opt_short=None, opt_long=None, type='int',
                  dest='x_pos', default=-1, help='Last X Position',
                  ini_group='position', ini_name='x')
  opts.add_option(opt_short=None, opt_long=None, type='int',
                  dest='y_pos', default=-1, help='Last Y Position',
                  ini_group='position', ini_name='y')

  opts.add_option_group(_('Developer Options'), _('These options are for developers.'))
  opts.add_option(opt_long='--loglevel', dest='loglevel', type='str', default='',
                  help=_('Logging level'))
  opts.add_option(opt_short='-d', opt_long='--debug', dest='debug', type='bool',
                  default=False,
                  help=_('Output debugging information. '
                         'Shorthand for --loglevel=debug'))
  return opts


def main():
  """Run the program."""
  # Check for --loglevel, --debug, we deal with them by ourselves because
  # option parser also use logging.
  loglevel = None
  for idx, arg in enumerate(sys.argv):
    if '--loglevel' in arg:
      if '=' in arg:
        loglevel = arg.split('=')[1]
      else:
        loglevel = sys.argv[idx + 1]
      level = getattr(logging, loglevel.upper(), None)
      if level is None:
          raise ValueError('Invalid log level: %s' % loglevel)
      loglevel = level
  else:
    if '--debug' in sys.argv or '-d' in sys.argv:
      loglevel = logging.DEBUG
  logging.basicConfig(
      level=loglevel,
      format='%(filename)s [%(lineno)d]: %(levelname)s %(message)s')
  if loglevel is None:
    # Disabling warning, info, debug messages
    logging.disable(logging.WARNING)

  opts = create_options()
  opts.read_ini_file(os.path.join(settings.get_config_dir(), 'config'))
  desc = _('Usage: %prog [Options...]')
  opts.parse_args(desc, sys.argv)

  opts.themes = settings.get_themes()
  if opts.theme and opts.theme not in opts.themes:
    print _('Theme %r does not exist') % opts.theme
    print
    print _('Please make sure %r can be found in '
            'one of the following directories:') % opts.theme
    print
    for theme_dir in settings.get_config_dirs('themes'):
      print ' - %s' % theme_dir
    sys.exit(-1)
  if opts.reset:
    print _('Resetting to defaults.')
    opts.reset_to_defaults()
    opts.save()
  keymon = KeyMon(opts)
  try:
    gtk.main()
  except KeyboardInterrupt:
    keymon.quit_program()

if __name__ == '__main__':
  #import cProfile
  #cProfile.run('main()', 'keymonprof')
  main()
