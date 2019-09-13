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
import xmlrpclib
import numpy as np
import iio
from ping import ping


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
        self._attached = False
        self._proxy = None
        self._iioctx = None
        self._iio_device = None
        self._iio_buffer = None
        self._logger = logging.getLogger(self.__class__.__name__)

    def _show_iio_device_attributes(self):
        """ Print the attributes of the probe's IIO device.
            Private function to be used for debug purposes only.

        Args:
            None

        Returns:
            None

        """
        self._logger.debug("============= IIO Device Attributes =============")
        self._logger.debug("  ID: %s", self._iio_device.id)
        self._logger.debug("  Name: %s", self._iio_device.name)
        if  self._iio_device is iio.Trigger:
            self._logger.debug(
                "  Trigger: yes (rate: %u Hz)", self._iio_device.frequency)
        else:
            self._logger.debug("  Trigger: none")
        self._logger.debug(
            "  Device attributes found: %u", len(self._iio_device.attrs))
        for attr in self._iio_device.attrs:
            self._logger.debug(
                "    %s: %s", attr, self._iio_device.attrs[attr].value)
        self._logger.debug(
            "  Device debug attributes found: %u",
            len(self._iio_device.debug_attrs))
        for attr in self._iio_device.debug_attrs:
            self._logger.debug(
                "    %s: %s", attr, self._iio_device.debug_attrs[attr].value)
        self._logger.debug(
            "  Device channels found: %u",
            len(self._iio_device.channels))
        for chn in self._iio_device.channels:
            self._logger.debug("    Channel ID: %s", chn.id)
            if chn.name is None:
                self._logger.debug("    Channel name: (none)")
            else:
                self._logger.debug("    Channel name: %s", chn.name)
            self._logger.debug("    Channel direction: %s", (
                "output" if chn.output else 'input'))
            self._logger.debug(
                "    Channel attributes found: %u", len(chn.attrs))
            for attr in chn.attrs:
                self._logger.debug(
                    "      %s: %s", attr, chn.attrs[attr].value)
            self._logger.debug("")
        self._logger.debug("=================================================")


    def _create_iio_context(self, ip):
        """ Create an IIO context, through which data samples will be retrieved.

        Args:
            ip (string): network IP address of the ACME cape which ACME probe
                belongs to. May be either of format '192.168.1.2' or
                'baylibre-acme.local'.

        Returns:
            IIO Context object in case of success, None otherwise.

        """
        try:
            iioctx = iio.Context("ip:" + ip)
        except OSError:
            self._logger.critical("IIO connection to %s timed out!", ip)
            return None
        except:
            self._logger.critical(
                "Unexpected error during IIO context creation! (ip='%s')", ip)
            self._logger.debug(traceback.format_exc())
            return None
        self._logger.debug("IIO context created (ip='%s').", ip)
        return iioctx

    def _xmlrpc_server_connect(self, ip):
        """ Connect to ACME XMLRPC server. Required to retrieve ACME probe
            details not found in IIO device attributes.

        Args:
            ip (string): network IP address of the ACME cape which ACME probe
                belongs to. May be either of format '192.168.1.2' or
                'baylibre-acme.local'.

        Returns:
            XMLRPC ServerProxy object in case of success, None otherwise.

        """
        acme_server_address = "%s:%d" % (ip, 8000)
        self._logger.debug("ACME Server Address: %s", acme_server_address)
        try:
            proxy = xmlrpclib.ServerProxy(
                "http://%s/acme" % acme_server_address)
        except:
            self._logger.critical(
                "Failed to connect to ACME XMLRPC server at address '%s'!",
                acme_server_address)
            self._logger.debug(traceback.format_exc())
            return None
        self._logger.debug("Connected to ACME XMLRPC server.")
        return proxy

    def _get_probe_info(self, proxy, slot):
        """ Return information about the ACME probe attached to given slot.


        Args:
            proxy (XMLRPC ServerProxy object) : ACME XMLRPC server
            slot (int): ACME cape slot, in which the ACME probe is attached to
                (as labelled on the ACME cape).

        Returns:
            ACME probe information (string) as provided by ACME XMLRPC Server in
            case of success, None otherwise.

        """
        if proxy is None:
            self._logger.critical("Not yet connected to XMLRPC server!")
            return None
        try:
            info = proxy.info("%s" % slot)
        except:
            self._logger.critical(
                "unexpected error while retrieving slot %u info!", slot)
            return None
        if info.find('Failed') != -1:
            # Slot is not populated with a probe
            self._logger.debug("XMLRPC: slot %u is empty.", slot)
            return None
        self._logger.debug("XMLRPC: slot %u is populated.", slot)
        return info

    def _get_probe_type(self, info):
        """ Extract probe type from probe information string
            obtained via ACME XMLRPC server.

        Args:
            info (string): probe information obtained via ACME XMLRPC server.

        Returns:
            ACME probe type (string) in case of success,
            None otherwise.

        """
        if info is None:
            self._logger.critical("info == None!")
            return None
        self._logger.debug("probe info:\n%s", info)

        # Retrieve probe type
        if info.find("JACK") != -1:
            probe_type = "JACK"
        elif info.find("USB") != -1:
            probe_type = "USB"
        elif info.find("HE10") != -1:
            probe_type = "HE10"
        else:
            self._logger.critical("unknown probe type!")
            return None
        self._logger.debug("Probe type: %s", probe_type)
        return probe_type

    def _get_probe_shunt(self, info):
        """ Extract shunt resistor value from probe information string
            obtained via ACME XMLRPC server.

        Args:
            info (string): probe information obtained via ACME XMLRPC server.

        Returns:
            Shunt resistor value in micro-ohm (int) in case of success,
            None otherwise.

        """
        if info is None:
            self._logger.critical("info == None!")
            return None
        self._logger.debug("probe info:\n%s", info)

        # Retrieve shunt resistor value
        pos1 = info.find("R_Shunt:")
        if pos1 != -1:
            pos2 = info.find("uOhm")
            if pos2 != -1:
                shunt = int(info[pos1 + 9: pos2 - 1])
                self._logger.debug(
                    "Probe shunt resistor value: %u uOhm", shunt)
                return shunt
            self._logger.critical("probe shunt resistor value not found!")
            return None
        else:
            self._logger.critical("probe shunt resistor value not found!")
            return None

    def _probe_has_power_switch(self, info):
        """ Extract power switching capability from probe information string
            obtained via ACME XMLRPC server.

        Args:
            info (string): probe information obtained via ACME XMLRPC server.

        Returns:
            Return True if probe features power switching capability,
            False if not,
            None is case of failure.

        """
        if info is None:
            self._logger.critical("info == None!")
            return None
        self._logger.debug("probe info:\n%s", info)

        # Retrieve power switch capability
        if info.find("Has Power Switch") != -1:
            pwr_switch = True
        else:
            pwr_switch = False
        self._logger.debug("Probe has power switch: %s", pwr_switch)
        return pwr_switch

    def _find_iio_device_index(self, proxy, slot):
        """ ACME slots are labelled starting from 1,
            but IIO keeps only track of present devices, starting from 0.
            E.g. if there are 2 probes in slots 2 and 5,
            IIO context has only 2 devices at index 0 and 1.
            Therefore, need to map ACME slot to IIO device index.
            Browse ACME slots one by one to find which ones are populated and
            find the correct IIO device index.

        Args:
            proxy (XMLRPC ServerProxy object) : ACME XMLRPC server
            slot (int): ACME cape slot, in which the ACME probe is attached to
                (as labelled on the ACME cape).

        Returns:
            Return IIO device index (int) of the selected probe (>= 0),
            None if not found.

        """
        iio_device_idx = None
        for s in range(1, slot + 1):
            info = self._get_probe_info(proxy, s)
            if info is not None:
                if iio_device_idx is None:
                    iio_device_idx = 0
                else:
                    iio_device_idx = iio_device_idx + 1
        if iio_device_idx is None:
            self._logger.warning(
                "IIO device index for probe in slot %u not found.",
                slot)
        else:
            self._logger.debug(
                "IIO device index for probe in slot %u is %u.",
                slot, iio_device_idx)
        return iio_device_idx

    def attach(self):
        """ Check that the probe is reachable, then create IIO context and
            retrieve probe's characteristics.

        Args:
            None

        Returns:
            True in case of success, False otherwise.

        """
        # Check probe is connected to the network
        if ping(self._ip) is False:
            self._logger.critical(
                "Failed to ping probe with network address '%s'!", self._ip)
            return False
        self._logger.debug("Probe ping'ed.")

        # Create IIO Context
        self._iioctx = self._create_iio_context(self._ip)
        if self._iioctx is None:
            return False

        # Check probe is attached to given slot and retrieve its characteristics
        # using ACME XMLRPC server
        self._proxy = self._xmlrpc_server_connect(self._ip)
        if self._proxy is None:
            return False

        # Get probe information
        info = self._get_probe_info(self._proxy, self._slot)
        if info is None:
            return False
        self._type = self._get_probe_type(info)
        if self._type is None:
            return False
        self._shunt = self._get_probe_shunt(info)
        if self._shunt is None:
            return False
        self._pwr_switch = self._probe_has_power_switch(info)
        if self._pwr_switch is None:
            return False

        # Retrieve probe's IIO device index and save it
        iio_device_idx = self._find_iio_device_index(self._proxy, self._slot)
        if iio_device_idx is None:
            return False
        self._iio_device = self._iioctx.devices[iio_device_idx]
        self._attached = True
        self._show_iio_device_attributes()
        return True

    def is_attached(self):
        """ Return True if probe is attached, False otherwise.

        Args:
            None

        Returns:
            bool: True if probe is attached, False otherwise.

        """
        return self._attached

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
        try:
            self._iio_device.attrs["in_oversampling_ratio"].value = str(
                oversampling_ratio)
            self._logger.debug(
                "Oversampling ratio configured to %u.",
                oversampling_ratio)
        except:
            self._logger.critical(
                "Failed to configure oversampling ratio (%u)!",
                oversampling_ratio)
            self._logger.debug(traceback.format_exc())
            return False
        return True

    def enable_asynchronous_reads(self, enable):
        """ Enable asynchronous reads.

        Args:
            enable (bool): True to enable asynchronous reads,
                           False to disable asynchronous reads.

        Returns:
            bool: True if operation is successful, False otherwise.

        """
        try:
            if enable is True:
                self._iio_device.attrs["in_allow_async_readout"].value = "1"
                self._logger.debug("Asynchronous reads enabled.")
            else:
                self._iio_device.attrs["in_allow_async_readout"].value = "0"
                self._logger.debug("Asynchronous reads disabled.")
        except:
            self._logger.critical("Failed to configure asynchronous reads!")
            self._logger.debug(traceback.format_exc())
            return False
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
        self._iio_buffer = iio.Buffer(self._iio_device, samples_count, cyclic)
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

    def attach(self):
        """ Check that the probe is reachable, then create IIO context and
            retrieve probe's characteristics.

        Args:
            None

        Returns:
            bool: True

        """
        self._time_start = 0
        self._shunt = self._slot * 10000
        return True

    def is_attached(self):
        """ Return True if probe is attached, False otherwise.

        Args:
            None

        Returns:
            bool: True

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
