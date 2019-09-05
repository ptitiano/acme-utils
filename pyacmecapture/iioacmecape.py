#!/usr/bin/env python
""" Baylibre's ACME Probe Abstraction class.

Baylibre's ACME Probe Abstraction class.

Inspired by work done on the "iio-capture" tool done by:
    - Paul Cercueil <paul.cercueil@analog.com>,
and the work done on "pyacmegraph" tool done by:
    - Sebastien Jan <sjan@baylibre.com>.
"""


from __future__ import print_function
import struct
import traceback
import numpy as np
# import iio
import logging
from ping import ping


__app_name__ = "IIO ACME Probe Python Library"
__license__ = "MIT"
__copyright__ = "Copyright 2019, Baylibre SAS"
__date__ = "2019/08/29"
__author__ = "Patrick Titiano"
__email__ = "ptitiano@baylibre.com"
__contact__ = "ptitiano@baylibre.com"
__maintainer__ = "Patrick Titiano"
__status__ = "Development"
__version__ = "0.1"
__deprecated__ = False




class IIOAcmeProbe2(object):
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
        self._iio_buffer = None
        logging.debug("New ACME Probe with IP %s & slot %s" % (self._ip, self._slot))

    def _show_iio_device_attributes(self):
        logging.debug("======== IIO Device infos ========")
        logging.debug("To be completed...")
        logging.debug("==================================")
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
            through the probe and power the device).

        Args:
            enable (bool): True to power on the device,
                           False to power off the device.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        if self.has_power_switch() is True:
            logging.warning("enable_power() function not yet implemented!")
            if enable is True:
                # TODO (ptitiano@baylibre.com): implement feature
                print("TODO enable power")
                logging.debug("Power enabled.")
            else:
                # TODO (ptitiano@baylibre.com): implement feature
                print("TODO disable power")
                logging.debug("Power disabled.")
        else:
            logging.warn(1, "No power switch on this probe!")
            return False
        return True

    def set_oversampling_ratio(self, oversampling_ratio):
        """ Set the capture oversampling ratio of the probe.

        Args:
            oversampling_ratio (int): oversampling ratio

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        logging.warning("set_oversampling_ratio() function not yet implemented!")
        return True

    def enable_asynchronous_reads(self, enable):
        """ Enable asynchronous reads.

        Args:
            enable (bool): True to enable asynchronous reads,
                           False to disable asynchronous reads.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        logging.warning("enable_asynchronous_reads() function not yet implemented!")
        return True

    def get_sampling_frequency(self):
        """ Return the capture sampling frequency (in Hertz).

        Args:
            None

        Returns:
            int: capture sampling frequency (in Hertz).
                 Return 0 in case of error.

        """
        logging.warning("get_sampling_frequency() function not yet implemented!")
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
        self._iio_buffer = iio.Buffer(self._iio_device, samples_count, cyclic)
        if self._iio_buffer != None:
            logging.debug("Buffer (count=%d, cyclic=%s) allocated." % (
                samples_count, cyclic))
            return True
        logging.error("Failed to allocate buffer! (count=%d, cyclic=%s)" % (
            samples_count, cyclic))
        return False

    def enable_capture_channel(self, channel, enable):
        """ Enable/disable capture of selected channel.

        Args:
            channel (string): channel to capture ('voltage', 'current', or 'power')
            enable (bool): True to enable capture, False to disable it.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        try:
            iio_ch = self._iio_device.find_channel(CHANNEL_DICT[channel])
            if not iio_ch:
                logging.error("Channel %s (%s) not found!" % (
                    channel, CHANNEL_DICT[channel]))
                return False
            logging.debug("Channel %s (%s) found." % (
                channel, CHANNEL_DICT[channel]))
            if enable is True:
                iio_ch.enabled = True
                logging.debug(1, "Channel %s (%s) capture enabled." % (
                    channel, CHANNEL_DICT[channel]))
            else:
                iio_ch.enabled = False
                logging.debug(1, "Channel %s (%s) capture disabled." % (
                    channel, CHANNEL_DICT[channel]))
        except:
            if enable is True:
                logging.error("Failed to enable capture on channel %s (%s)!")
            else:
                logging.error("Failed to disable capture on channel %s (%s)!")
            logging.error(traceback.format_exc())
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
            logging.error("Failed to refill buffer!")
            logging.error(traceback.format_exc())
            return False
        logging.debug("Buffer refilled.")
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
            logging.debug("Channel %s: %u samples read." % (channel, len(values)))
            logging.debug("Channel %s samples       : %s" % (channel, str(values)))
            # Scale values
            logging.debug("Scale: %f" % scale)
            if scale != 1.0:
                scaled_values = np.asarray(values) * scale
            else:
                scaled_values = np.asarray(values)
            logging.debug("Channel %s scaled samples: %s" % (channel, str(scaled_values)))
        except:
            logging.error("Failed to read channel %s buffer!" % channel)
            logging.error(traceback.format_exc())
            return None
        return {"channel": channel,
                "unit": CHANNEL_UNITS[channel],
                "samples": scaled_values}
