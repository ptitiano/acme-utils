#!/usr/bin/env python
""" Baylibre's ACME Probe Abstraction class.

Baylibre's ACME Probe Abstraction class.

Inspired by work done on the "iio-capture" tool done by:
    - Paul Cercueil <paul.cercueil@analog.com>,
and the work done on "pyacmegraph" tool done by:
    - Sebastien Jan <sjan@baylibre.com>.

Todo:
    * Do implement/validate IIOAcmeProbe (only VirtualIIOAcmeProbe tested so far
"""


from __future__ import print_function
import struct
import traceback
from time import sleep
import logging
import numpy as np
from ping import ping
#import iio


__app_name__ = "IIO ACME Probe Python Library"
__license__ = "MIT"
__copyright__ = "Copyright 2018, Baylibre SAS"
__date__ = "2018/03/01"
__author__ = "Patrick Titiano"
__email__ = "ptitiano@baylibre.com"
__contact__ = "ptitiano@baylibre.com"
__maintainer__ = "Patrick Titiano"
__status__ = "Development"
__version__ = "0.4"
__deprecated__ = False


# Channels mapping: 'explicit naming' vs 'IIO channel IDs'
CHANNEL_DICT = {
    'Vshunt' : 'voltage0',
    'Vbat' : 'voltage1',
    'Time' : 'timestamp',
    'Ishunt' : 'current3',
    'Power' : 'power2'}

# Channels unit
CHANNEL_UNITS = {
    'Vshunt' : 'mV',
    'Vbat' : 'mV',
    'Time' : 'ns',
    'Ishunt' : 'mA',
    'Power' : 'mW'}


class IIOAcmeProbe(object):
    """ Represent Baylibre's ACME probe. Allow controlling it as an IIO device.

    This class is used to abstract Baylibre's ACME probe,
    controlling it as an IIO device.

    """
    def _is_up(self):
        """ Check if the ACME cape is up and running.

        Args:
            None

        Returns:
            bool: True if ACME cape is operational, False otherwise.

        """
        return ping(self._ip)

    def __init__(self, ip, slot, name=None):
        """ Initialise IIOAcmeProbe class

        Args:
            ip (string): network IP address of the ACME cape which ACME probe
                belongs to. May be either of format '192.168.1.2' or
                'baylibre-acme.local'.
            slot (int): ACME cape slot, in which the ACME probe is attached to
                (as labelled on the ACME cape).
            name (string): optional name (label) for the probe.
                Default name when not provided by user is 'ip-slot'.

        Returns:
            None

        """
        if name != None:
            self._name = name
        else:
            self._name = ip + '-' + str(slot)
        self._ip = ip
        self._slot = slot
        self._type = None
        self._shunt = None
        self._pwr_switch = None
        self._iioctx = None
        self._iio_device = None
        self._iio_buffer = None
        self._logger = logging.getLogger("IIOAcmeProbe")
        self._logger.debug(
            "New ACME Probe with IP %s & slot %s",
            self._ip, self._slot)

    def _show_iio_device_attributes(self):
        self._logger.debug("======== IIO Device infos ========")
        self._logger.warning("To be completed...")
        self._logger.debug("==================================")
        return True

    def name(self):
        """ Return the name of the probe.

        Args:
            None

        Returns:
            string: the name of the probe

        """
        return self._name

    def slot(self):
        """ Return the slot number (int) in which the probe is attached.

        Args:
            None

        Returns:
            int: slot number

        """
        return self._slot

    def type(self):
        """ Return the probe type (string).

        Args:
            None

        Returns:
            string: probe type ('JACK', 'USB', or 'HE10')

        """
        return self._type

    def shunt(self):
        """ Return the shunt resistor value of the probe (int, in micro-ohm)

        Args:
            None

        Returns:
            int: shunt resistor value (in micro-ohm)

        """
        return self._shunt

    def has_power_switch(self):
        """ Return True if the probe is equipped with a power switch,
            False otherwise.

        Args:
            None

        Returns:
            bool: True if the probe is equipped with a power switch,
                  False otherwise.

        """
        return self._pwr_switch

    def enable_power(self, enable):
        """ Enable the power switch of the probe (i.e. let the current go
            through the probe and power the Device Under Test (DUT)).

        Args:
            enable (bool): True to power on the DUT,
                           False to power off the DUT.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        if self.has_power_switch() is True:
            self._logger.warning("enable_power() function not yet implemented!")
            if enable is True:
                # TODO (ptitiano@baylibre.com): implement feature
                print("TODO enable power")
                self._logger.info("Power enabled.")
            else:
                # TODO (ptitiano@baylibre.com): implement feature
                print("TODO disable power")
                self._logger.info("Power disabled.")
        else:
            self._logger.warning("This probe has no power switch!")
            return False
        return True

    def set_oversampling_ratio(self, oversampling_ratio):
        """ Set the capture oversampling ratio of the probe.

        Args:
            oversampling_ratio (int): oversampling ratio

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        self._logger.warning(
            "set_oversampling_ratio() function not yet implemented!")
        return True

    def enable_asynchronous_reads(self, enable):
        """ Enable asynchronous reads.

        Args:
            enable (bool): True to enable asynchronous reads,
                           False to disable asynchronous reads.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        self._logger.warning(
            "enable_asynchronous_reads() function not yet implemented!")
        return True

    def get_sampling_frequency(self):
        """ Return the capture sampling frequency (in Hertz).

        Args:
            None

        Returns:
            int: capture sampling frequency (in Hertz).
                 Return 0 in case of error.

        """
        self._logger.warning(
            "get_sampling_frequency() function not yet implemented!")
        return 0

    def allocate_capture_buffer(self, samples_count, cyclic=False):
        """ Allocate buffer to store captured data.

        Args:
            samples_count (int): amount of samples to hold in buffer (> 0).
            cyclic (bool): True to make the buffer act as a circular buffer,
                           False otherwise.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        # self._iio_buffer = iio.Buffer(self._iio_device, samples_count, cyclic)
        if self._iio_buffer != None:
            self._logger.debug(
                "Buffer (count=%d, cyclic=%s) allocated.",
                samples_count, cyclic)
            return True
        self._logger.error(
            "Failed to allocate buffer! (count=%d, cyclic=%s)",
            samples_count, cyclic)
        return False

    def enable_capture_channel(self, channel, enable):
        """ Enable/disable capture of selected channel.

        Args:
            channel (string): channel to capture
                ('voltage', 'current', or 'power')
            enable (bool): True to enable capture, False to disable it.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        try:
            iio_ch = self._iio_device.find_channel(CHANNEL_DICT[channel])
            if not iio_ch:
                self._logger.error(
                    "Channel %s (%s) not found!",
                    channel, CHANNEL_DICT[channel])
                return False
            self._logger.debug(
                "Channel %s (%s) found.", channel, CHANNEL_DICT[channel])
            if enable is True:
                iio_ch.enabled = True
                self._logger.debug(
                    "Channel %s (%s) capture enabled.",
                    channel, CHANNEL_DICT[channel])
            else:
                iio_ch.enabled = False
                logging.debug(
                    "Channel %s (%s) capture disabled.",
                    channel, CHANNEL_DICT[channel])
        except:
            if enable is True:
                self._logger.error(
                    "Failed to enable capture on channel %s (%s)!",
                    channel, CHANNEL_DICT[channel])
            else:
                self._logger.error(
                    "Failed to disable capture on channel %s (%s)!",
                    channel, CHANNEL_DICT[channel])
            self._logger.debug(traceback.format_exc())
            return False
        return True

    def refill_capture_buffer(self):
        """ Fill capture buffer with new samples.

        Args:
            None

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        try:
            self._iio_buffer.refill()
        except:
            self._logger.warning("Failed to refill buffer!")
            self._logger.debug(traceback.format_exc())
            return False
        self._logger.debug("Buffer refilled.")
        return True

    def read_capture_buffer(self, channel):
        """ Return the samples stored in the capture buffer of selected channel.
            Take care of data scaling too.

        Args:
            channel (string): capture channel ('voltage', 'current', or 'power')

        Returns:
            dict: a dictionary holding the scaled data, with the following keys:
                  "channel" (string): channel,
                  "unit" (string): data unit,
                  "samples" (int or float): scaled samples.

        """
        try:
            # Retrieve channel
            iio_ch = self._iio_device.find_channel(CHANNEL_DICT[channel])
            # Retrieve samples (raw)
            ch_buf_raw = iio_ch.read(self._iio_buffer)
            if CHANNEL_DICT[channel] != 'timestamp':
                # Retrieve channel scale
                scale = float(iio_ch.attrs['scale'].value)
                # Configure binary data format to unpack (16-bit signed integer)
                unpack_str = 'h' * (len(ch_buf_raw) / struct.calcsize('h'))
            else:
                # No scale attribute on 'timestamp' channel
                scale = 1.0
                # Configure binary data format to unpack (64-bit signed integer)
                unpack_str = 'q' * (len(ch_buf_raw) / struct.calcsize('q'))
            # Unpack data
            values = struct.unpack(unpack_str, ch_buf_raw)
            self._logger.debug(
                "Channel %s: %u samples read.", channel, len(values))
            self._logger.debug(
                "Channel %s samples       : %s", channel, str(values))
            # Scale values
            self._logger.debug("Scale: %f", scale)
            if scale != 1.0:
                scaled_values = np.asarray(values) * scale
            else:
                scaled_values = np.asarray(values)
            self._logger.debug(
                "Channel %s scaled samples: %s", channel, str(scaled_values))
        except:
            self._logger.error("Failed to read channel %s buffer!", channel)
            self._logger.error(traceback.format_exc())
            return None
        return {"channel": channel,
                "unit": CHANNEL_UNITS[channel],
                "samples": scaled_values}


class VirtualIIOAcmeProbe(IIOAcmeProbe):
    """ Simulate Baylibre's ACME probe.

    This class is used to abstract and simulate Baylibre's ACME probe.

    """
    def __init__(self, ip, slot, name=None):
        """ Initialise VirtualIIOAcmeProbe.

        Args:
            ip (string): network IP address of the ACME cape. May be either
                of format '192.168.1.2' or 'baylibre-acme.local'.
            slot (int): ACME cape slot, in which the ACME probe is attached to
                (as labelled on the ACME cape).
            name (string): optional name (label) for the probe.
                Default name when not provided by user is 'ip-slot'.

        Returns:
            None

        """
        if name != None:
            self._name = name
        else:
            self._name = ip + '-' + str(slot)
        self._ip = ip
        self._slot = slot
        self._type = None
        self._shunt = self._slot * 10000
        self._pwr_switch = None
        self._iioctx = None
        self._iio_buffer = None
        self._samples_count = 0
        self._time_start = 0
        self._logger = logging.getLogger("VirtualIIOAcmeProbe")
        self._logger.debug(
            "New ACME Probe parameters: IP:%s, slot:%s, name: %s",
            self._ip, self._slot, self._name)

    def is_up(self):
        """ Check if the ACME probe is up and running.

        Args:
            None

        Returns:
            bool: True if ACME probe is operational, False otherwise.

        """
        return True

    def enable_power(self, enable):
        """ Enable the power switch of the probe (i.e. let the current go
            through the probe and power the Device Under Test (DUT)).

        Args:
            enable (bool): True to power on the DUT,
                           False to power off the DUT.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        if self.has_power_switch() is True:
            if enable is True:
                self._logger.debug("Power enabled.")
            else:
                self._logger.debug("Power disabled.")
        else:
            self._logger.warning("This probe has no power switch!")
            return False
        return True

    def set_oversampling_ratio(self, oversampling_ratio):
        """ Set the capture oversampling ratio of the probe.

        Args:
            oversampling_ratio (int): oversampling ratio

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        return True

    def enable_asynchronous_reads(self, enable):
        """ Enable asynchronous reads.

        Args:
            enable (bool): True to enable asynchronous reads,
                           False to disable asynchronous reads.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        return True

    def allocate_capture_buffer(self, samples_count, cyclic=False):
        """ Allocate buffer to store captured data.

        Args:
            samples_count (int): amount of samples to hold in buffer (> 0).
            cyclic (bool): True to make the buffer act as a circular buffer,
                           False otherwise.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        self._samples_count = samples_count
        return True

    def enable_capture_channel(self, channel, enable):
        """ Enable/disable capture of selected channel.

        Args:
            channel (string): channel to capture ('voltage', 'current', or 'power')
            enable (bool): True to enable capture, False to disable it.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        return True

    def refill_capture_buffer(self):
        """ Fill capture buffer with new samples.

        Args:
            None

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        sleep(0.5)
        self._logger.debug("Buffer refilled.")
        return True

    def read_capture_buffer(self, channel):
        """ Return the samples stored in the capture buffer of selected channel.
            Take care of data scaling too.

        Args:
            channel (string): capture channel ('voltage', 'current', or 'power')

        Returns:
            dict: a dictionary holding the scaled data, with the following keys:
                  "channel" (string): channel,
                  "unit" (string): data unit,
                  "samples" (int or float): scaled samples.

        """
        if channel == "Time":
            buff = {"channel": channel,
                    "unit": CHANNEL_UNITS[channel],
                    "samples": range(self._time_start,
                                     self._time_start +
                                     (1000000 * self._samples_count),
                                     1000000)}
            self._time_start += 1000000 * self._samples_count
        elif channel == "Vbat":
            buff = {"channel": channel,
                    "unit": CHANNEL_UNITS[channel],
                    "samples": [1000 * float(self._slot)] * self._samples_count}
        else:
            buff = {"channel": channel,
                    "unit": CHANNEL_UNITS[channel],
                    "samples": [float(self._slot)] * self._samples_count}
        return buff
