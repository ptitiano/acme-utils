#!/usr/bin/env python
""" Python ACME Power Capture Utility

This utility is designed to capture voltage, current and power samples with
Baylibre's ACME Power Measurement solution (www.baylibre.com/acme).

Inspired by work done on the "iio-capture" tool done by:
    - Paul Cercueil <paul.cercueil@analog.com>,
    - Marc Titinger <mtitinger@baylibre.com>,
    - Fabrice Dreux <fdreux@baylibre.com>,
and the work done on "pyacmegraph" tool done by:
    - Sebastien Jan <sjan@baylibre.com>.

Leveraged IIOAcmeProbe classes abstracting IIO/ACME details.

Todo:
    * Fix Segmentation fault at end of script
    * Find a way to remove hard-coded power unit (uW)
    * Allow capture to be interrupted before end and still return results
"""


from __future__ import print_function
import traceback
import sys
import os
import argparse
import threading
import logging
from time import time, localtime, strftime
import numpy as np
from iioacmeprobe import IIOAcmeProbe, VirtualIIOAcmeProbe


__app_name__ = "Python ACME Power Capture Utility"
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


_OVERSAMPLING_RATIO = 1
_ASYNCHRONOUS_READS = False
_CAPTURED_CHANNELS = ["Time", "Vbat", "Ishunt"]
_REPORT_1ST_COL_WIDTH = 13
_REPORT_COLS_WIDTH_MIN = 7
_REPORT_COL_PAD = 2
_LOGGER_NAME = "pyacmecapture"

# create logger
_LOGGER = logging.getLogger(_LOGGER_NAME)
_VERBOSE_LOGLEVEL = logging.DEBUG - 5


def exit_with_error(err):
    """ Display completion message with error code before terminating execution.

    Args:
        err (int): an error code

    Returns:
        None

    """
    print()
    if err != 0:
        _LOGGER.error("Script execution terminated with error code %d.", err)
    else:
        _LOGGER.info("Script execution successfully completed.")
    print("\n< There may be a 'Segmentation fault (core dumped)' error message after this one. >")
    print("< This is a kwown bug. Please ignore it. >\n")
    exit(err)


def verbose(msg, *args, **kwargs):
    """ Logs a message with custom level VERBOSE.

    Args:
        msg (string): message format string
        args (strings): arguments which are merged into msg
            using the string formatting operator
        kwargs (strings): optional keyword arguments

    Returns:
        None

    """
    if logging.getLogger().isEnabledFor(_VERBOSE_LOGLEVEL):
        _LOGGER.log(_VERBOSE_LOGLEVEL, msg)


class IIODeviceCaptureThread(threading.Thread):
    """ IIO ACME Capture thread

    This class is used to abstract the capture of multiple channels of a single
    ACME probe / IIO device.

    """

    def __init__(self, probe, channels, bufsize, duration):
        """ Initialise IIODeviceCaptureThread class

        Args:
            probe: IIOAcmeProbe instance
            channels (list of strings): channels to capture
                        Supported channels: 'Vshunt', 'Vbat', 'Ishunt', 'Power'
            bufsize (int): capture buffer size (in samples)
            duration (int): capture duration (in seconds)

        Returns:
            None

        """
        threading.Thread.__init__(self)
        # Init internal variables
        self._probe = probe
        self._channels = channels
        self._bufsize = bufsize
        self._duration = duration
        self._timestamp_thread_start = None
        self._thread_execution_time = None
        self._refill_start_times = None
        self._refill_end_times = None
        self._read_start_times = None
        self._read_end_times = None
        self._failed = None
        self._samples = None

        _LOGGER.debug(
            "Thread parameters: probe=%s channels=%s buffer size=%u duration="
            "%us", self._probe.name(), self._channels,
            self._bufsize, self._duration)

    def _log(self, loglevel, msg, *args, **kwargs):
        """ Print log messages, prefixed with thread name

        Args:
            loglevel (int): level or severity of the event to track
            msg (string): message to log

        Returns:
            None

        """
        _LOGGER.log(loglevel, "[Thread %s] %s", self._probe.name(), msg)

    def configure_capture(self):
        """ Configure capture parameters (enable channel(s),
            configure internal settings, ...)

        Args:
            None

        Returns:
            bool: True if successful, False otherwise.

        """
        # Set oversampling for max perfs (4 otherwise)
        if self._probe.set_oversampling_ratio(_OVERSAMPLING_RATIO) is False:
            self._log(logging.ERROR, "Failed to set oversampling ratio!")
            return False
        self._log(logging.DEBUG, "Oversampling ratio set to %u." % \
            _OVERSAMPLING_RATIO)

        # Disable asynchronous reads
        if self._probe.enable_asynchronous_reads(_ASYNCHRONOUS_READS) is False:
            self._log(logging.ERROR, "Failed to configure asynchronous reads!")
            return False
        self._log(logging.DEBUG, "Asynchronous reads set to %s." % \
            _ASYNCHRONOUS_READS)

        # Enable selected channels
        for ch in self._channels:
            ret = self._probe.enable_capture_channel(ch, True)
            if ret is False:
                self._log(logging.ERROR, "Failed to enable %s capture!" % ch)
                return False
            else:
                self._log(logging.DEBUG, "%s capture enabled."  % ch)

        # Allocate capture buffer
        if self._probe.allocate_capture_buffer(self._bufsize) is False:
            self._log(logging.ERROR, "Failed to allocate capture buffer!")
            return False
        self._log(logging.DEBUG, "Capture buffer allocated.")

        return True

    def run(self):
        """ Capture samples for the selected duration. Save samples in a
            dictionary as described in get_samples() docstring.

        Args:
            None

        Returns:
            True when operation is completed.

        """
        self._failed = False
        self._samples = {}
        self._refill_start_times = []
        self._refill_end_times = []
        self._read_start_times = []
        self._read_end_times = []
        for ch in self._channels:
            self._samples[ch] = None
            self._samples["name"] = self._probe.name()
            self._samples["channels"] = self._channels
            self._samples["duration"] = self._duration

        self._timestamp_thread_start = time()
        elapsed_time = 0
        while elapsed_time < self._duration:
            # Capture samples
            self._refill_start_times.append(time())
            ret = self._probe.refill_capture_buffer()
            self._refill_end_times.append(time())
            if ret != True:
                self._log(logging.WARNING, "Error during buffer refill!")
                self._failed = True
            # Read captured samples
            self._read_start_times.append(time())
            for ch in self._channels:
                s = self._probe.read_capture_buffer(ch)
                if s is None:
                    self._log(
                        logging.WARNING, "Error during %s buffer read!" % ch)
                    self._failed = True
                if self._samples[ch] is not None:
                    self._samples[ch]["samples"] = np.append(
                        self._samples[ch]["samples"], s["samples"])
                else:
                    self._samples[ch] = {}
                    self._samples[ch]["failed"] = False
                    self._samples[ch]["unit"] = s["unit"]
                    self._samples[ch]["samples"] = s["samples"]
                self._log(
                    _VERBOSE_LOGLEVEL, "self._samples[%s] = %s" % (
                        ch, str(self._samples[ch])))
            self._read_end_times.append(time())
            elapsed_time = time() - self._timestamp_thread_start
        self._thread_execution_time = time() - self._timestamp_thread_start
        self._samples[ch]["failed"] = self._failed
        self._log(logging.DEBUG, "done.")
        return True

    def print_runtime_stats(self):
        """ Print various capture runtime-collected stats.
            Since printing traces from multiple threads causes mixed and
            confusing trace, it is preferable to collect data and print it
            afterwards. For debug purpose only.

        Args:
            None

        Returns:
            None

        """
        self._log(
            _VERBOSE_LOGLEVEL,
            "------------------------- Runtime Stats -------------------------")
        self._log(
            _VERBOSE_LOGLEVEL,
            "Execution time: %s" % self._thread_execution_time)
        # Convert list to numpy array
        self._refill_start_times = np.asarray(self._refill_start_times)
        self._refill_end_times = np.asarray(self._refill_end_times)
        self._read_start_times = np.asarray(self._read_start_times)
        self._read_end_times = np.asarray(self._read_end_times)
        # Make timestamps relative to first one, and convert to ms
        first_refill_start_time = self._refill_start_times[0]
        self._refill_start_times -= first_refill_start_time
        self._refill_start_times *= 1000
        self._refill_end_times -= first_refill_start_time
        self._refill_end_times *= 1000

        first_read_start_time = self._read_start_times[0]
        self._read_start_times -= first_read_start_time
        self._read_start_times *= 1000
        self._read_end_times -= first_read_start_time
        self._read_end_times *= 1000
        # Compute refill and read durations
        refill_durations = np.subtract(
            self._refill_end_times, self._refill_start_times)
        read_durations = np.subtract(
            self._read_end_times, self._read_start_times)

        # Print time each time buffer was getting refilled
        self._log(
            _VERBOSE_LOGLEVEL, "Buffer Refill start times (ms): %s" % \
            self._refill_start_times)
        self._log(
            _VERBOSE_LOGLEVEL, "Buffer Refill end times (ms): %s" % \
            self._refill_end_times)
        # Print time spent refilling buffer
        self._log(
            _VERBOSE_LOGLEVEL,
            "Buffer Refill duration (ms): %s" % refill_durations)
        if len(self._refill_start_times) > 1:
            # Print buffer refill time stats
            refill_durations_min = np.amin(refill_durations)
            refill_durations_max = np.amax(refill_durations)
            refill_durations_avg = np.average(refill_durations)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Buffer Refill Duration (ms): min=%s max=%s avg=%s" % (
                    refill_durations_min,
                    refill_durations_max,
                    refill_durations_avg))
            # Print delays between 2 consecutive buffer refills
            refill_delays = np.ediff1d(self._refill_start_times)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Delay between 2 Buffer Refill (ms): %s" % refill_delays)
            # Print buffer refill delay stats
            refill_delays_min = np.amin(refill_delays)
            refill_delays_max = np.amax(refill_delays)
            refill_delays_avg = np.average(refill_delays)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Buffer Refill Delay (ms): min=%s max=%s avg=%s" % (
                    refill_delays_min,
                    refill_delays_max,
                    refill_delays_avg))

        # Print time each time buffer was getting read
        self._log(
            _VERBOSE_LOGLEVEL,
            "Buffer Read start times (ms): %s" % self._read_start_times)
        self._log(
            _VERBOSE_LOGLEVEL,
            "Buffer Read end times (ms): %s" % self._read_end_times)
        # Print time spent reading buffer
        self._log(
            _VERBOSE_LOGLEVEL, "Buffer Read duration (ms): %s" % read_durations)
        if len(self._read_start_times) > 1:
            # Print buffer read time stats
            read_durations_min = np.amin(read_durations)
            read_durations_max = np.amax(read_durations)
            read_durations_avg = np.average(read_durations)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Buffer Read Duration (ms): min=%s max=%s avg=%s" % (
                    read_durations_min,
                    read_durations_max,
                    read_durations_avg))
            # Print delays between 2 consecutive buffer reads
            read_delays = np.ediff1d(self._read_start_times)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Delay between 2 Buffer Read (ms): %s" % read_delays)
            # Print buffer read delay stats
            read_delays_min = np.amin(read_delays)
            read_delays_max = np.amax(read_delays)
            read_delays_avg = np.average(read_delays)
            self._log(
                _VERBOSE_LOGLEVEL,
                "Buffer Read Delay (ms): min=%s max=%s avg=%s" % (
                    read_delays_min,
                    read_delays_max,
                    read_delays_avg))
        self._log(
            _VERBOSE_LOGLEVEL,
            "-----------------------------------------------------------------")

    def get_samples(self):
        """ Return collected samples. To be called once thread completed.

        Args:
            None

        Returns:
            dict: a dictionary (one per channel) containing following key/data:
                "name" (string): ACME probe name
                "channels" (list of strings): channels captured
                "duration" (int): capture duration (in seconds)
                For each captured channel:
                "capture channel name" (dict): a dictionary containing following key/data:
                    "failed" (bool): False if successful, True otherwise
                    "samples" (array): captured samples
                    "unit" (str): captured samples unit}}
            E.g:
                {'name': 'VDD1', 'channels': ['Vbat', 'Ishunt'], 'duration': 3,
                 'Vbat': {'failed': False, 'samples': array([ 1, 2, 3 ]), 'unit': 'mV'},
                 'Ishunt': {'failed': False, 'samples': array([4, 5, 6 ]), 'unit': 'mA'}}

        """
        return self._samples

def main():
    """ Capture power measurements of selected ACME probe(s) over IIO link.

    Refer to argparse code to learn about available commandline options.

    Returns:
        int: error code (0 in case of success, a negative value otherwise)

    """
    err = -1

    # Print application header
    print(__app_name__ + " (version " + __version__ + ")\n")

    # Parse user arguments
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=
        '''This tool captures min, max, and average values of selected
           power rails (voltage, current, power).
           These power measurements are performed using Baylibre's
           ACME cape and probes, over the network using IIO lib.

           Example usage:
           $ ''' + sys.argv[0] +
        ''' --probes 192.168.1.2:1,3,5..8 baylibre-acme.local:2 --names C1-VDD1 C1-VDD3 C1-VDD5 C1-VDD6 C1-VDD7 C1-VDD8 C2-VDD2 --duration 5''')

    parser.add_argument(
        '--probes', '-p', metavar='PROBES', nargs='+',
        default='baylibre-acme.local:1..8',
        help='''List of ACME probes to sample, using following syntax:
                hostname1:slot(s),hostname2:slot(s)
                Hostname may be either IP address or network name
                (e.g. 192.168.1.2 or baylibre-acme.local).
                To specify multiple hostnames, separate each hostname with
                a comma.
                slot(s) is the cape's slot(s) the probe is connected to,
                as labelled on the cape. It always starts from 1.
                slot(s) may be a single one, a range, or a list of
                non-consecutive slots.
                To specify a range of slots, specify the first and last slots,
                separated with '..' (e.g. 4..8).
                To specify a list of non-consecutive slots, separate each slot
                with a comma (e.g. 1,2,5).''')

    parser.add_argument('--names', '-n', metavar='LABELS', default=None,
                        nargs='+',
                        help='''List of names for the captured power rails
                        (one name per power rail,
                        following same order as '--probes').
                        E.g. VDD_BAT VDD_ARM VDD_SOC VDD_GPU''')

    parser.add_argument('--duration', '-d', metavar='SEC', type=int,
                        default=10, help='Capture duration in seconds (> 0).')
    parser.add_argument('--bufsize', '-b', metavar='BUFFER SIZE', type=int,
                        default=127, help='Capture buffer size (in samples).')

    parser.add_argument(
        '--outdir', '-od', metavar='OUTPUT DIRECTORY',
        default=None,
        help='''Output directory where report and trace files will be saved
                (default: $HOME/pyacmecapture/yyyymmdd-hhmmss/).''')
    parser.add_argument(
        '--out', '-o', metavar='OUTPUT FILE', default=None,
        help='''Output file name (default: date (yyyymmdd-hhmmss''')
    parser.add_argument('--nofile', '-x', action="store_true", default=False,
                        help='''Do not export report and trace files.''')

    parser.add_argument('--virtual', action="store_true", default=False,
                        help='''Use a virtual cape (SW-simulated,
                        no real HW access).
                        Use for development purposes only.''')

    parser.add_argument(
        '--loglevel', '-l', metavar='LOGLEVEL', default='WARNING',
        help='''Logging level (valid: 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', VERBOSE).
                Default log level: 'WARNING'.
                Use custom level "VERBOSE" to print internal data.''')

    args = parser.parse_args()

    # Configure logging level
    args.loglevel = args.loglevel.upper()
    logging.addLevelName(_VERBOSE_LOGLEVEL, "VERBOSE")
    _LOGGER.verbose = verbose
    if args.loglevel == 'VERBOSE':
        logging.basicConfig(
            format='%(levelname)s: %(name)s: %(message)s',
            name=_LOGGER_NAME, level=_VERBOSE_LOGLEVEL)
    elif args.loglevel == 'DEBUG':
        logging.basicConfig(
            format='%(levelname)s: %(name)s: %(message)s',
            name=_LOGGER_NAME, level=logging.DEBUG)
    else:
        numeric_level = getattr(logging, args.loglevel, None)
        if not isinstance(numeric_level, int):
            logging.basicConfig(
                format='%(levelname)s: %(message)s',
                level=logging.ERROR)
            _LOGGER.error("Invalid log level! ('%s')", args.loglevel)
            exit_with_error(err)
        else:
            logging.basicConfig(
                format='%(levelname)s: %(message)s',
                level=numeric_level)

    # Parse user arguments and check that they are valid
    _LOGGER.debug("User arguments: %s", str(args)[10:-1])
    # Check duration and buffer size are valid
    try:
        assert args.duration > 0
    except:
        _LOGGER.error("Wrong user argument ('duration')")
        exit_with_error(err)
    try:
        assert args.bufsize > 0
    except:
        _LOGGER.error("Wrong user argument ('bufsize')")
        exit_with_error(err)
    err = err - 1
    # Retrieve probes list and names
    # Accepted formats: (and any combinations of these)
    #   ip:slot
    #   ip:slotA,slotB,slotC
    #   ip:slotStart..SlotEnd
    #   ip:slotA,slotB ip:slotC
    probes = []
    # Retrieve probe IP and slot
    for probe in args.probes:
        try:
            probe = probe.split(':')
            ip = probe[0]
            slots = probe[1].split(',')
            for slot in slots:
                if '..' not in slot:
                    probes.append({"ip": ip, "slot": int(slot), 'name': None})
                else:
                    slot_range = slot.split('..')
                    probes.append({
                        "ip": ip, "slot": int(slot_range[0]), 'name': None})
                    slot_range = range(
                        int(slot_range[0]) + 1, int(slot_range[1]) + 1, 1)
                    for i in slot_range:
                        probes.append({"ip": ip, "slot": i, 'name': None})
        except:
            _LOGGER.error("Failed to parse probes!")
            _LOGGER.debug(traceback.format_exc())
            exit_with_error(err)
    _LOGGER.debug("probe list: %s", probes)
    # Add name to probe
    if args.names is not None:
        try:
            assert len(args.names) == len(probes)
        except:
            _LOGGER.error(
                "names count (%u) do not match probes count (%u)!",
                len(args.names), len(probes))
            exit_with_error(err)
        for i, name in enumerate(args.names):
            probes[i]['name'] = name
    else:
        for probe in probes:
            probe['name'] = probe['ip'] + '-' + str(probe['slot'])
    _LOGGER.debug("probe list with names: %s", probes)

    _LOGGER.info("User arguments parsed.")
    err = err - 1

    # Create IIOAcmeProbe instance(s)
    try:
        for probe in probes:
            if args.virtual is False:
                probe['dev'] = IIOAcmeProbe(
                    probe['ip'], probe['slot'], probe['name'])
            else:
                probe['dev'] = VirtualIIOAcmeProbe(
                    probe['ip'], probe['slot'], probe['name'])
    except:
        _LOGGER.critical("ACME Probe instance instantiation failed!")
        _LOGGER.debug("failed probe: %s", probe)
        _LOGGER.debug(traceback.format_exc())
        exit_with_error(err)
    _LOGGER.info("ACME Probe instance(s) instantiated.")
    err = err - 1

    # Attach to probe(s)
    for probe in probes:
        if probe['dev'].attach() is True:
            _LOGGER.debug(
                "ACME Probe '%s' attached.", probe['name'])
        else:
            _LOGGER.critical(
                "Failed to attach to ACME probe '%s'!", probe['name'])
            exit_with_error(err)

    _LOGGER.info("ACME Probe(s) attached.")
    err = err - 1

    # Create output directory (if doesn't exist)
    now = strftime("%Y%m%d-%H%M%S", localtime())
    if args.nofile is False:
        if args.outdir is None:
            outdir = os.path.join(os.path.expanduser('~/pyacmecapture'), now)
        else:
            outdir = args.outdir
        _LOGGER.debug("Output directory: %s", outdir)

        if args.out is None:
            report_filename = os.path.join(outdir, now + "-report.txt")
        else:
            report_filename = os.path.join(outdir, args.out + "-report.txt")
        _LOGGER.debug("Report filename: %s", report_filename)

        try:
            os.makedirs(outdir)
        except OSError as e:
            if e.errno == os.errno.EEXIST:
                _LOGGER.debug("Directory '%s' already exists.", outdir)
            else:
                _LOGGER.error("Failed to create output directory")
                _LOGGER.debug(traceback.format_exc())
                exit_with_error(err)
        except:
            _LOGGER.error("Failed to create output directory")
            _LOGGER.debug(traceback.format_exc())
            exit_with_error(err)
        _LOGGER.info("Output directory created.")
    err = err - 1

    # Create and configure capture threads
    for probe in probes:
        # Instantiate a new capture thread per probe
        try:
            thread = IIODeviceCaptureThread(
                probe['dev'], _CAPTURED_CHANNELS, args.bufsize, args.duration)
        except:
            _LOGGER.error(
                "Failed to instantiate capture thread for probe '%s'!",
                probe['name'])
            _LOGGER.debug(traceback.format_exc())
            exit_with_error(err)
        _LOGGER.debug(
            "Capture thread for probe '%s' instantiated.", probe['name'])
        # Configure new capture thread
        try:
            ret = thread.configure_capture()
        except:
            _LOGGER.error(
                "Failed to configure capture thread for probe '%s'!",
                probe['name'])
            _LOGGER.debug(traceback.format_exc())
            exit_with_error(err)
        if ret is False:
            _LOGGER.error(
                "Failed to configure capture thread for probe '%s'!",
                probe['name'])
            exit_with_error(err)
        probe['thread'] = thread
        _LOGGER.debug("Capture thread for probe '%s' configured.", probe['name'])
    err = err - 1

    # Start capture threads
    try:
        for probe in probes:
            probe['thread'].start()
    except:
        _LOGGER.critical("Failed to start capture!")
        _LOGGER.debug(traceback.format_exc())
        exit_with_error(err)
    _LOGGER.info("Capture started.")
    err = err - 1

    # Wait for capture threads to complete
    for probe in probes:
        probe['thread'].join()
    _LOGGER.info("Capture completed.")

    for probe in probes:
        probe['thread'].print_runtime_stats()

    # Retrieve captured data
    for probe in probes:
        probe['samples'] = probe['thread'].get_samples()
        _LOGGER.verbose(
            "Probe %s captured data: %s" % (probe['name'], probe['samples']))
    _LOGGER.info("Captured samples retrieved.")

    # Process samples
    for probe in probes:
        # Make time samples relative to first sample
        #FIXME Handle single timestamp corner case
        first_timestamp = probe['samples']["Time"]["samples"][0]
        probe['samples']["Time"]["samples"] -= first_timestamp
        timestamp_diffs = np.ediff1d(probe['samples']["Time"]["samples"])
        timestamp_diffs_ms = timestamp_diffs / 1000000
        _LOGGER.verbose(
            "Probe %s timestamp_diffs (ms): %s" % (
                probe['name'], timestamp_diffs_ms))
        timestamp_diffs_min = np.amin(timestamp_diffs_ms)
        timestamp_diffs_max = np.amax(timestamp_diffs_ms)
        timestamp_diffs_avg = np.average(timestamp_diffs_ms)
        _LOGGER.verbose(
            "Probe %s Time difference between 2 samples (ms): "
            "min=%u max=%u avg=%u" % (
                probe['name'],
                timestamp_diffs_min,
                timestamp_diffs_max,
                timestamp_diffs_avg))
        real_capture_time_ms = probe['samples']["Time"]["samples"][-1] / 1000000
        sample_count = len(probe['samples']["Time"]["samples"])
        real_sampling_rate = sample_count / (real_capture_time_ms / 1000.0)
        _LOGGER.verbose(
            "Probe %s: real capture duration: %u ms (%u samples)" % (
                probe['name'], real_capture_time_ms, sample_count))
        _LOGGER.verbose(
            "Probe %s: real sampling rate: %u Hz" % (
                probe['name'], real_sampling_rate))

        # Compute Power (P = Vbat * Ishunt)
        probe['samples']["Power"] = {}
        probe['samples']["Power"]["unit"] = "mW" # FIXME
        probe['samples']["Power"]["samples"] = np.multiply(
            probe['samples']["Vbat"]["samples"],
            probe['samples']["Ishunt"]["samples"])
        probe['samples']["Power"]["samples"] /= 1000.0
        _LOGGER.verbose(
            "Probe %s power samples: %s" % (
                probe['name'], probe['samples']["Power"]["samples"]))

        # Compute min, max, avg values for Vbat, Ishunt and Power
        probe['samples']["Vbat min"] = np.amin(probe['samples']["Vbat"]["samples"])
        probe['samples']["Vbat max"] = np.amax(probe['samples']["Vbat"]["samples"])
        probe['samples']["Vbat avg"] = np.average(probe['samples']["Vbat"]["samples"])
        probe['samples']["Ishunt min"] = np.amin(probe['samples']["Ishunt"]["samples"])
        probe['samples']["Ishunt max"] = np.amax(probe['samples']["Ishunt"]["samples"])
        probe['samples']["Ishunt avg"] = np.average(probe['samples']["Ishunt"]["samples"])
        probe['samples']["Power min"] = np.amin(probe['samples']["Power"]["samples"])
        probe['samples']["Power max"] = np.amax(probe['samples']["Power"]["samples"])
        probe['samples']["Power avg"] = np.average(probe['samples']["Power"]["samples"])
    _LOGGER.info("Captured samples processed.")

    # Generate report
    # Use a dictionary to map table cells with data elements
    table = {}
    table['rows'] = ['Name', 'Shunt (mohm)',
                     'Voltage', ' Min (mV)', ' Max (mV)', ' Avg (mV)',
                     'Current', ' Min (mA)', ' Max (mA)', ' Avg (mA)',
                     'Power', ' Min (mW)', ' Max (mW)', ' Avg (mW)']
    table['data_keys'] = {}
    table['data_keys']['Voltage'] = None
    table['data_keys'][' Min (mV)'] = 'Vbat min'
    table['data_keys'][' Max (mV)'] = 'Vbat max'
    table['data_keys'][' Avg (mV)'] = 'Vbat avg'
    table['data_keys']['Current'] = None
    table['data_keys'][' Min (mA)'] = 'Ishunt min'
    table['data_keys'][' Max (mA)'] = 'Ishunt max'
    table['data_keys'][' Avg (mA)'] = 'Ishunt avg'
    table['data_keys']['Power'] = None
    table['data_keys'][' Min (mW)'] = 'Power min'
    table['data_keys'][' Max (mW)'] = 'Power max'
    table['data_keys'][' Avg (mW)'] = 'Power avg'

    report = []
    # Add misc details to report header
    report.append("Date: %s" % now)
    report.append("Pyacmecapture version: %s" % __version__)
    report.append("Captured Channels: %s" % _CAPTURED_CHANNELS)
    report.append("Oversampling ratio: %u" % _OVERSAMPLING_RATIO)
    report.append("Asynchronous reads: %s" % _ASYNCHRONOUS_READS)
    report.append("Power Rails: %u" % len(probes))
    report.append("Duration: %us\n" % args.duration)

    # Adjust column width with name so that it's never truncated
    cols_width = []
    for probe in probes:
        cols_width.append(
            _REPORT_COL_PAD + max(_REPORT_COLS_WIDTH_MIN, len(probe['name'])))

    # Generate report
    for row in table['rows']:
        line = row.ljust(_REPORT_1ST_COL_WIDTH)
        for i in range(len(probes)):
            if 'Name' in row:
                line += probes[i]['name'].rjust(cols_width[i])
            elif 'Shunt (mohm)' in row:
                line += str(probes[i]['dev'].shunt() / 1000).rjust(
                    cols_width[i])
            elif table['data_keys'][row] is not None:
                line += format(probes[i]['samples'][table['data_keys'][row]], '.1f').rjust(
                    cols_width[i])
        report.append(line)

    # Add output filenames to report
    if args.nofile is False:
        report.append("\nReport file: %s" % report_filename)
        for probe in probes:
            if args.out is None:
                trace_filename = now
            else:
                trace_filename = args.out
            trace_filename += "_"
            trace_filename += probe['name']
            trace_filename += ".csv"
            trace_filename = os.path.join(outdir, trace_filename)
            report.append("%s Trace file: %s" % (
                probe['name'], trace_filename))
            probe['trace_filename'] = trace_filename
    report_max_length = len(max(report, key=len))
    dash_count = (report_max_length - len(" Power Measurement Report ")) / 2

    # Add dashlines at beginning and end of report
    if report_max_length % 2 == 0:
        report.insert(0,
                      "-" * dash_count +
                      " Power Measurement Report " +
                      "-" * dash_count)
    else:
        report.insert(0,
                      "-" * dash_count +
                      " Power Measurement Report " +
                      "-" * (dash_count + 1))
    report.append("-" * report_max_length)

    # Save report to file
    if args.nofile is False:
        try:
            of_report = open(report_filename, 'w')
            for line in report:
                print(line, file=of_report)
            of_report.close()
        except:
            _LOGGER.error("Failed to save Power Measurement report!")
            _LOGGER.debug(traceback.format_exc())
            exit_with_error(err)
        _LOGGER.info("Power Measurement report saved.")

    # Save Power Measurement trace to file (CSV format)
    if args.nofile is False:
        for probe in probes:
            try:
                of_trace = open(probe['trace_filename'], 'w')
            except:
                _LOGGER.info(
                    "Failed to create output trace file %s",
                    probe['trace_filename'])
                _LOGGER.debug(traceback.format_exc())
                exit_with_error(err)

            # Format trace header (name columns)
            s = "Time (%s),%s Voltage (%s),%s Current (%s),%s Power (%s)" % (
                probe['samples']["Time"]["unit"],
                probe['name'], probe['samples']["Vbat"]["unit"],
                probe['name'], probe['samples']["Ishunt"]["unit"],
                probe['name'], probe['samples']["Power"]["unit"])
            print(s, file=of_trace)
            # Save samples in trace file
            for j in range(len(probe['samples']["Ishunt"]["samples"])):
                s = "%s,%s,%s,%s" % (
                    probe['samples']["Time"]["samples"][j],
                    probe['samples']["Vbat"]["samples"][j],
                    probe['samples']["Ishunt"]["samples"][j],
                    probe['samples']["Power"]["samples"][j])
                print(s, file=of_trace)
            of_trace.close()
            _LOGGER.info(
                "%s Power Measurement Trace saved in %s.",
                probe['name'], probe['trace_filename'])

    # Display report
    print()
    for line in report:
        print(line)

    # Done
    exit_with_error(0)

if __name__ == '__main__':
    main()
