# Programmed by Jason Whitfield

import sys
import os
import binascii

import serial.tools.list_ports
from serial import Serial

# pyserial library
# https://pypi.python.org/pypi/pyserial
# Copyright (c) 2001-2015 Chris Liechti <cliechti@gmx.net> All Rights Reserved.
# license: https://pythonhosted.org/pyserial/appendix.html#license

from PyQt5 import QtCore, QtGui

# PyQt4 library
# https://www.riverbankcomputing.com/software/pyqt/download
# Copyright (c) 2015 Riverbank Computing Limited
# licensed under GNU GPL v3
# http://www.gnu.org/licenses/gpl-3.0.en.html

from pyqtgraph import PlotWidget

# pyqtgraph library
# http://www.pyqtgraph.org/
# Copyright (c) 2012  University of North Carolina at Chapel Hill
# Luke Campagnola - luke.campagnola@gmail.com
# licensed under the MIT open-source license
# https://opensource.org/licenses/mit-license.php

# Constants that control communication with arduino.
READY_COMMAND   = b'\x00'
READ_COMMAND    = b'\x01'
PIN_COMMAND     = b'\x02'
RATE_COMMAND    = b'\x03'
TRIGGER_COMMAND = b'\x04'

# Rate of communication and timeout for serial communication with arduino.
BAUD_RATE = 115200
TIMEOUT   = 3

# Default Y axis for graph.
GRAPH_RANGE_Y = 5

class Window(QtGui.QWidget):

  # Default application settings. 
  period = 30
  analog_channel = 0
  trigger_channel = 8
  rate_index = 0
  out_string = 'Data'
  directory = os.path.dirname(os.path.realpath(__file__)) + '/data'
  settings_port = ''

  # Initialization of application variables.
  volts = []
  times = []
  port_name = ''
  last_multiple = period
  time = 0
  sweep = 0
  reading = False

  def __init__(self, parent=None):
    super(Window, self).__init__(parent)

    # Replace default settings with settings from file.
    self.readSettings();

    # Initialize serial communication.
    self.ser = Serial()
    self.ser.baudrate = BAUD_RATE
    self.ser.timeout = TIMEOUT

    # Create graph for plotting data. Disable mouse by default.
    self.graph = PlotWidget()
    self.graph.hideAxis('bottom')
    self.graph.showAxis('bottom')
    self.graph.setMouseEnabled(False, False)
    self.graph.hideButtons()
    self.graph.setYRange(0, GRAPH_RANGE_Y)
    self.graph.setXRange(0, self.period)

    # Create user interface elements and connect them to corresponding functions.
    self.start_button = QtGui.QPushButton('Start')
    self.start_button.clicked.connect(self.startPlot)

    self.stop_button = QtGui.QPushButton('Stop')
    self.stop_button.clicked.connect(self.stopPlot)
    self.stop_button.setEnabled(False)
    self.stop_button.setCheckable(True)

    channel_label = QtGui.QLabel('Analog Channel')

    self.channel_box = QtGui.QSpinBox()
    self.channel_box.setValue(self.analog_channel)
    self.channel_box.valueChanged.connect(self.channel)
    self.channel(self.analog_channel)
    
    trigger_label = QtGui.QLabel('Trigger Channel')

    self.trigger_box = QtGui.QSpinBox()
    self.trigger_box.setValue(self.trigger_channel)
    self.trigger_box.valueChanged.connect(self.trigger)
    self.trigger(self.trigger_channel)

    rate_label = QtGui.QLabel('Data Acquisition Rate (Hz)')

    self.rate_box = QtGui.QComboBox()
    self.rate_box.addItems(['10', '20', '50', '100', '200', '250', '500'])
    self.rate_box.setCurrentIndex(self.rate_index);
    self.rate_box.currentIndexChanged.connect(self.refresh)
    self.refresh(self.rate_index)

    port_label = QtGui.QLabel('Serial Port')

    self.port_box = QtGui.QComboBox()
    # Find valid ports.
    self.refreshPorts()
    self.port_box.currentIndexChanged.connect(self.portChanged)
    # Check if previously used port is still valid.
    if self.settings_port != '':
      index = self.port_box.findText(self.settings_port)
      if index > -1:
        self.port_box.setCurrentIndex(index)
      else:
        self.port_name = ''

    self.refresh_button = QtGui.QPushButton('Refresh Ports')
    self.refresh_button.clicked.connect(self.refreshPorts)

    period_label = QtGui.QLabel('Graph Period (s)')

    self.period_box = QtGui.QSpinBox()
    self.period_box.setMaximum(1000000)
    self.period_box.setValue(self.period)
    self.period_box.valueChanged.connect(self.changePeriod)

    output_label = QtGui.QLabel('Data Output Prefix')

    self.output_edit = QtGui.QLineEdit()
    self.output_edit.setText(self.out_string)
    self.output_edit.editingFinished.connect(self.outputString)

    self.dir_button = QtGui.QPushButton('Choose Data Directory')
    self.dir_button.clicked.connect(self.chooseDirectory)
    
    # Add user interface elements to panel.
    button_box = QtGui.QVBoxLayout()
    button_box.addWidget(port_label)
    button_box.addWidget(self.port_box)
    button_box.addWidget(self.refresh_button)
    button_box.addWidget(channel_label)
    button_box.addWidget(self.channel_box)
    button_box.addWidget(trigger_label)
    button_box.addWidget(self.trigger_box)
    button_box.addWidget(rate_label)
    button_box.addWidget(self.rate_box)
    button_box.addWidget(period_label)
    button_box.addWidget(self.period_box)
    button_box.addWidget(output_label)
    button_box.addWidget(self.output_edit)
    button_box.addWidget(self.dir_button)
    # Displace start and stop buttons to bottom of panel.
    button_box.addStretch(1)
    button_box.addWidget(self.start_button)
    button_box.addWidget(self.stop_button)

    # Place panel on left side of application and graph on right.
    layout = QtGui.QHBoxLayout()
    layout.addLayout(button_box)
    layout.addWidget(self.graph, 1)

    self.setLayout(layout)

    # Create timers to control repeating functions.
    self.plot_timer = QtCore.QTimer(self)
    self.plot_timer.timeout.connect(self.plot)

    self.read_timer = QtCore.QTimer(self)
    self.read_timer.timeout.connect(self.read)
    
    self.trigger_timer = QtCore.QTimer(self)
    self.trigger_timer.timeout.connect(self.checkTrigger)
    self.trigger_timer.start()

  def refreshPorts(self):
    # Loop through com ports and try to open each.
    self.port_box.clear()
    for p in serial.tools.list_ports.comports():
      try:
        self.openPort(p[0])
        # If the port opened, add it to the list.
        if (self.ser.read() == READY_COMMAND):
          self.port_box.addItem(p[0])
      except:
        pass
    if self.port_box.count() ==  0:
      self.port_name = ''
    
  def closeEvent(self, event):
    # When user closes application, stop reading and save settings.
    if self.reading:
      self.stopPlot()

    settings = open(os.path.dirname(os.path.realpath(__file__)) + '/settings.dat', 'w+')
    
    settings.write('PORT=' + self.port_name + '\n')
    settings.write('ANALOG_CHANNEL=' + str(self.analog_channel) + '\n')
    settings.write('DATA_RATE=' + str(self.rate_index) + '\n')
    settings.write('PERIOD=' + str(self.period) + '\n')
    settings.write('PREFIX=' + self.out_string + '\n')
    settings.write('DIRECTORY=' + self.directory + '\n')

    settings.close()
    event.accept()

  def read(self): 
    # If full transmission of 6 bytes is available, read data from arduino.
    #print(self.ser.inWaiting())
    if (self.ser.inWaiting() >= 6):
      # Convert reading to voltage by using conversion factor 1 bit = 0.125 mV.
      volt = (4.096*int(binascii.hexlify(self.ser.read(2)),16)/32768.0)
      #volt = 4.096*(int(self.ser.read(2).encode('hex'), 16)/32768.0)

      # Convert time reading from microseconds to seconds.
      #self.time += (int(self.ser.read(4).encode('hex'), 16)/1000000.0)
      self.time += (int(binascii.hexlify(self.ser.read(4)),16)/1000000.0)
      
      # If graph has reached edge, reset with new sweep.
      if (self.time > self.last_multiple):
        self.last_multiple += self.period
        self.newSweep()

      # Add readings to lists of readings.
      self.times.append(self.time)
      self.volts.append(volt)

  def plot(self):
    # Plot current lists of data on graph after clearing previous graph.
    self.graph.plot(self.times, self.volts, clear=True)

  def startPlot(self):
    if self.port_name == '':
      # If no ports are available, inform user and end function.
      warn = QtGui.QMessageBox()
      warn.setWindowTitle('Warning')
      warn.setText('No open ports.')
      warn.exec_()
      return
    if not self.ping():
      # If currently selected port is not open, warn user and end function.
      warn = QtGui.QMessageBox()
      warn.setWindowTitle('Warning')
      warn.setText('Could not connect to port: ' + self.ser.port)
      warn.exec_()
      return
    if (self.period * int(self.rate_box.itemText(self.rate_box.currentIndex())) > 20000):
      # If the user chose too large of a period, inform user and end function.
      # This is in place to avoid memory issues caused by overly large lists of data.
      warn = QtGui.QMessageBox()
      warn.setWindowTitle('Warning')
      warn.setText('Period too large for current data acquisition rate.\n\n'\
              'Maximum Periods:\n'\
              '10\tHz\t\t\t2,000\ts\n'\
              '20\tHz\t\t\t1,000\ts\n'\
              '50\tHz\t\t\t400\ts\n'\
              '100\tHz\t\t\t200\ts\n'\
              '200\tHz\t\t\t100\ts\n'\
              '250\tHz\t\t\t80\ts\n'\
              '500\tHz\t\t\t40\ts')
      warn.exec_()
      return

    self.reading = True

    # Send current pin and data rate to the arduino.
    self.ser.write(PIN_COMMAND)
    self.ser.write(bytes(str(self.analog_channel),'utf_8'))
    self.ser.write(b'\n')

    self.ser.write(RATE_COMMAND)
    self.ser.write(bytes(str(int(self.rate_box.itemText(self.rate_index))),'utf_8'))
    self.ser.write(b'\n')

    # Reset data lists and graph variables to starting values.
    self.volts = []
    self.times = []
    self.sweep = 0
    self.time = 0
    self.last_multiple = self.period
    self.graph.setXRange(0, self.period)

    # Disable all user interface elements that should not be changed while acquiring data.
    self.start_button.setEnabled(False)
    self.channel_box.setEnabled(False)
    self.trigger_box.setEnabled(False)
    self.rate_box.setEnabled(False)
    self.period_box.setEnabled(False)
    self.port_box.setEnabled(False)
    self.output_edit.setEnabled(False)
    self.dir_button.setEnabled(False)

    # Enable stop button.
    self.stop_button.setEnabled(True)

    # Tell arduino to start reading, and start the timers to read and plot data.
    self.ser.write(READ_COMMAND)
    self.ser.flushInput()
    # Graph updates at 50 Hz to smoothly graph while avoiding performance issues.
    self.plot_timer.start(20)
    self.read_timer.start()

  def stopPlot(self):
    # Export the current sweep to data file.
    self.autoExport()
    if self.reading:
      # Stop timers from reading and plotting data.
      #self.plot_timer.stop()
      #self.read_timer.stop()
      self.reading = False  

    # Re-enable user interface.
    self.start_button.setEnabled(True)
    self.channel_box.setEnabled(True)
    self.trigger_box.setEnabled(True)
    self.rate_box.setEnabled(True)
    self.period_box.setEnabled(True)
    self.port_box.setEnabled(True)
    self.output_edit.setEnabled(True)
    self.dir_button.setEnabled(True)

    # Disable stop button.
    self.stop_button.setEnabled(False)

    # If connection was not lost, tell arduino to stop reading.
    try:
      self.ser.write(READ_COMMAND)
      #self.ser.write(b'\n')
    except:
      pass

    # Stop timers from reading and plotting data.
    self.plot_timer.stop()
    self.read_timer.stop()

  def channel(self, new_channel):
    # Controls which channel arduino should read from.
    self.analog_channel = new_channel
    
  def trigger(self, new_channel):
    # Controls which channel arduino should read trigger from.
    self.trigger_channel = new_channel
    if self.ping():
      self.ser.write(TRIGGER_COMMAND)
      self.ser.write(bytes(self.trigger_channel))
      self.ser.write(b'\n')

  def refresh(self, rate_index):
    # Controls rate arduino should read at.
    self.rate_index = rate_index

  def openPort(self, port_name):
    # Close current port, reinitialize to new port, and attempt to open new port.
    self.ser.close()
    self.port_name = port_name
    self.ser.port = port_name
    self.ser.open()

  def portChanged(self, port_index):
    # When new port is chosen from list, try to open it.
    try:
      name = str(self.port_box.itemText(port_index))
      if self.port_name != name:
        self.openPort(name)
    except:
      pass

  def newSweep(self):
    # When graph reaches edge, dump data to file and reset for new sweep.
    self.autoExport()
    self.times = []
    self.volts = []
    self.sweep += 1
    self.graph.setXRange(self.period*self.sweep, self.period*(self.sweep+1))

  def autoExport(self):
    # Checks specified directory for data. If it doesn't exist, it is created.
    dir = self.directory + '/' + self.out_string
    if not os.path.exists(dir):
      os.makedirs(dir)
    # Creates or opens data file corresponding to current sweep of graph.
    f = open(dir + '/' + self.out_string + '_' + ('%03d' % self.sweep) + '.txt', 'w')
    # Writes data to that file.
    for time, volt in zip(self.times, self.volts):
      f.write(str(time)+'\t'+str(volt)+'\n')
    f.close()

  def changePeriod(self, new_period):
    # Changes period of graph and sweep.
    self.period = new_period
    self.last_multiple = new_period
    self.graph.setXRange(0, new_period)

  def outputString(self):
    # Changes prefix of data files.
    self.out_string = str(self.output_edit.text())

  def chooseDirectory(self):
    # Opens dialog for user to choose where to save data.
    new_dir = str(QtGui.QFileDialog.getExistingDirectory(self, 'Select Directory'))
    if (new_dir):
      self.directory = new_dir

  def readSettings(self):
    # Open or create settings file.
    path = os.path.dirname(os.path.realpath(__file__)) + '/settings.dat'
    if os.path.exists(path):
      settings = open(path, 'r+')
    else:
      settings = open(path, 'w+')
    # Parse through file and read settings.
    for line in settings.readlines():
      key, value = line.split('=')
      value = value.rstrip()
      if (key == 'PORT'):
        self.settings_port = value
      elif (key == 'ANALOG_CHANNEL'):
        self.analog_channel = int(value)
      elif (key == 'DATA_RATE'):
        self.rate_index = int(value)
      elif (key == 'PERIOD'):
        self.period = int(value)
      elif (key == 'PREFIX'):
        self.out_string = value
      elif (key == 'DIRECTORY'):
        self.directory = value
    settings.close()
  
  def ping(self):
    # Check if arduino is still connected.
    try:
      self.ser.write(READY_COMMAND)
      return True
    except:
      return False
      
  def checkTrigger(self):
    #print(self.reading)
    '''
    #print(self.plot_timer.timerId())
    while self.reading == False and self.port_name != '':
      print("this stopped")
      #print(self.ser.inWaiting())
      self.plot_timer.stop()
      self.read_timer.stop()
      self.reading = False
      #if self.plot_timer.timerId() == -1 and self.read_timer.timerId() == -1 and self.ser.inWaiting:
      #  break
    #  if not self.ser.inWaiting():
    #    break
    '''
	
    if not self.reading and self.port_name != '' and self.ser.inWaiting() and not self.stop_button.isChecked():
      if self.ser.read() == READ_COMMAND:
        self.startPlot()
        self.ser.flushInput()
		
    #if self.plot_timer.timerId() == -1 and self.read_timer.timerId() == -1:
    #  self.stop_button.setChecked(0)


if __name__ == '__main__':
  app = QtGui.QApplication(sys.argv)

  main = Window()
  main.setWindowTitle('Arduino Data Logger')
  main.show()

  sys.exit(app.exec_())
