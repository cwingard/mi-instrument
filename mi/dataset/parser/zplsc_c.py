#!/usr/bin/env python

"""
@package mi.dataset.parser.zplsc_c
@file /mi/dataset/parser/zplsc_c.py
@author Rene Gelinas
@brief Parser for the zplsc_c dataset driver

This file contains code for the zplsc_c parser and code to produce data particles.

The ZPLSC sensor, series C, provides acoustic return measurements from the water column.
The recovered data files (*.01A) are binary recovered from the CF flash memory.
The file may contain record data for multiple phases and bursts of measurements.
Mal-formed sensor data records produce no particles.

All data are in unsigned integer format, with exception of the first 2 delimiter characters.
The sensor data record has a header followed by the scientific data.  The format of the header
is defined in the AzfpProfileHeader class below.

The format of the scientific data is as follows:
Bytes    Description
------   ---------------
# Bins   Data Channel 1
# Bins   Data Channel 2
# Bins   Data Channel 3
# Bins   Data Channel 4

Data that is stored as 16 bit digitized data is stored as consecutive 16 bit values.
The number is defined by the # of bins or NumBins.

Averaged data is summed up linear scale data that is stored in NumBins * 32 bit unsigned
integer sums, this is followed by NumBins * 8 bit Overflow counts.


Release notes:

Initial Release
"""

import struct
import exceptions
import os
import numpy as np
from ctypes import *
from mi.core.exceptions import SampleException, RecoverableSampleException
from mi.core.instrument.dataset_data_particle import DataParticle, DataParticleKey
from mi.core.log import get_logger, get_logging_metaclass
from mi.dataset.dataset_parser import SimpleParser
from mi.core.common import BaseEnum
from datetime import datetime
from mi.common.zpls_plot import ZPLSPlot
from mi.dataset.driver.zplsc_c.zplsc_c_echogram import ZPLSCCEchogram

log = get_logger()
METACLASS = get_logging_metaclass('trace')

__author__ = 'Rene Gelinas'
__license__ = 'Apache 2.0'


PROFILE_DATA_DELIMITER = '\xfd\x02'  # Byte Offset 0 and 1


class DataParticleType(BaseEnum):
    # ZPLSC_C_PARTICLE_TYPE = 'zplsc_c_recovered'
    ZPLSC_C_PARTICLE_TYPE = 'zplsc_echogram_data'


class ZplscCParticleKey(BaseEnum):
    """
    Class that defines fields that need to be extracted for the data particle.
    """
    TRANS_TIMESTAMP = "zplsc_c_transmission_timestamp"
    SERIAL_NUMBER = "serial_number"
    PHASE = "zplsc_c_phase"
    BURST_NUMBER = "burst_number"
    TILT_X = "zplsc_c_tilt_x_counts"
    TILT_Y = "zplsc_c_tilt_y_counts"
    BATTERY_VOLTAGE = "zplsc_c_battery_voltage_counts"
    TEMPERATURE = "zplsc_c_temperature_counts"
    PRESSURE = "zplsc_c_pressure_counts"
    IS_AVERAGED_DATA = "zplsc_c_is_averaged_data"
    FREQ_CHAN_1 = "zplsc_frequency_channel_1"
    VALS_CHAN_1 = "zplsc_values_channel_1"
    DEPTH_CHAN_1 = "zplsc_depth_range_channel_1"
    FREQ_CHAN_2 = "zplsc_frequency_channel_2"
    VALS_CHAN_2 = "zplsc_values_channel_2"
    DEPTH_CHAN_2 = "zplsc_depth_range_channel_2"
    FREQ_CHAN_3 = "zplsc_frequency_channel_3"
    VALS_CHAN_3 = "zplsc_values_channel_3"
    DEPTH_CHAN_3 = "zplsc_depth_range_channel_3"
    FREQ_CHAN_4 = "zplsc_frequency_channel_4"
    VALS_CHAN_4 = "zplsc_values_channel_4"
    DEPTH_CHAN_4 = "zplsc_depth_range_channel_4"


class ZplscCRecoveredDataParticle(DataParticle):
    __metaclass__ = METACLASS

    def __init__(self, *args, **kwargs):
        super(ZplscCRecoveredDataParticle, self).__init__(*args, **kwargs)
        self._data_particle_type = DataParticleType.ZPLSC_C_PARTICLE_TYPE

    def _build_parsed_values(self):
        """
        Build parsed values for Instrument Data Particle.
        @return: list containing type encoded "particle value id:value" dictionary pairs
        """
        # Particle Mapping table, where each entry is a tuple containing the particle
        # field name, count(or count reference) and a function to use for data conversion.

        port_timestamp = self.raw_data[ZplscCParticleKey.TRANS_TIMESTAMP]
        self.contents[DataParticleKey.PORT_TIMESTAMP] = port_timestamp

        return [{DataParticleKey.VALUE_ID: name, DataParticleKey.VALUE: None}
                if self.raw_data[name] is None else
                {DataParticleKey.VALUE_ID: name, DataParticleKey.VALUE: value}
                for name, value in self.raw_data.iteritems()]


class AzfpProfileHeader(BigEndianStructure):
    _pack_ = 1                              # 124 bytes in the header (includes the 2 byte delimiter)
    _fields_ = [                            # V Byte Offset (from delimiter)
        ('burst_num', c_ushort),            # 002 - Burst number
        ('serial_num', c_ushort),           # 004 - Instrument Serial number
        ('ping_status', c_ushort),          # 006 - Ping Status
        ('burst_interval', c_uint),         # 008 - Burst Interval (seconds)
        ('year', c_ushort),                 # 012 - Year
        ('month', c_ushort),                # 014 - Month
        ('day', c_ushort),                  # 016 - Day
        ('hour', c_ushort),                 # 018 - Hour
        ('minute', c_ushort),               # 020 - Minute
        ('second', c_ushort),               # 022 - Second
        ('hundredths', c_ushort),           # 024 - Hundreths of a second
        ('digitization_rate', c_ushort*4),  # 026 - Digitization Rate (channels 1-4) (64000, 40000 or 20000)
        ('lockout_index', c_ushort*4),      # 034 - The sample number of samples skipped at start of ping (channels 1-4)
        ('num_bins', c_ushort*4),           # 042 - Number of bins (channels 1-4)
        ('range_samples', c_ushort*4),      # 050 - Range samples per bin (channels 1-4)
        ('num_pings_profile', c_ushort),    # 058 - Number of pings per profile
        ('is_averaged_pings', c_ushort),    # 060 - Indicates if pings are averaged in time
        ('num_pings_burst', c_ushort),      # 062 - Number of pings that have been acquired in this burst
        ('ping_period', c_ushort),          # 064 - Ping period in seconds
        ('first_ping', c_ushort),           # 066 - First ping number (if averaged, first averaged ping number)
        ('second_ping', c_ushort),          # 068 - Last ping number (if averaged, last averaged ping number)
        ('is_averaged_data', c_ubyte*4),    # 070 - 1 = averaged data (5 bytes), 0 = not averaged (2 bytes)
        ('error_num', c_ushort),            # 074 - Error number if an error occurred
        ('phase', c_ubyte),                 # 076 - Phase used to acquire this profile
        ('is_overrun', c_ubyte),            # 077 - 1 if an over run occurred
        ('num_channels', c_ubyte),          # 078 - Number of channels (1, 2, 3 or 4)
        ('gain', c_ubyte*4),                # 079 - Gain (channels 1-4) 0, 1, 2, 3 (Obsolete)
        ('spare', c_ubyte),                 # 083 - Spare
        ('pulse_length', c_ushort*4),       # 084 - Pulse length (channels 1-4) (uS)
        ('board_num', c_ushort*4),          # 092 - Board number of the data (channels 1-4)
        ('frequency', c_ushort*4),          # 100 - Board frequency (channels 1-4)
        ('is_sensor_available', c_ushort),  # 108 - Indicate if pressure/temperature sensor is available
        ('tilt_x', c_ushort),               # 110 - Tilt X (counts)
        ('tilt_y', c_ushort),               # 112 - Tilt Y (counts)
        ('battery_voltage', c_ushort),      # 114 - Battery voltage (counts)
        ('pressure', c_ushort),             # 116 - Pressure (counts)
        ('temperature', c_ushort),          # 118 - Temperature (counts)
        ('ad_channel_6', c_ushort),         # 120 - AD channel 6
        ('ad_channel_7', c_ushort)          # 122 - AD channel 7
        ]


def generate_image_file_path(filepath, output_path=None):
    # Extract the file time from the file name
    absolute_path = os.path.abspath(filepath)
    filename = os.path.basename(absolute_path).upper()
    directory_name = os.path.dirname(absolute_path)

    output_path = directory_name if output_path is None else output_path
    image_file = filename.replace('.01A', '.png')
    return os.path.join(output_path, image_file)


class ZplscCCalibrationCoefficients(object):
    # TODO: This class should be replaced by methods to get the CCs from the system.
    DS = list()

    # Freq 38kHz
    DS.append(2.280000038445e-2)

    # Freq 125kHz
    DS.append(2.280000038445e-2)

    # Freq 200kHz
    DS.append(2.250000089407e-2)

    # Freq 455kHz
    DS.append(2.300000004470e-2)


class ZplscCParser(SimpleParser):
    def __init__(self, config, stream_handle, exception_callback):
        super(ZplscCParser, self).__init__(config, stream_handle, exception_callback)
        self._particle_type = None
        self._gen = None
        self.ph = None  # The profile header of the current record being processed.
        self.cc = ZplscCCalibrationCoefficients()
        self.is_first_record = True
        self.hourly_avg_temp = 0
        self.zplsc_echogram = ZPLSCCEchogram()

    def find_next_record(self):
        good_delimiter = True
        delimiter = self._stream_handle.read(2)
        while delimiter not in [PROFILE_DATA_DELIMITER, '']:
            good_delimiter = False
            delimiter = delimiter[1:2]
            delimiter += self._stream_handle.read(1)

        if not good_delimiter:
            self._exception_callback('Invalid record delimiter found.\n')

    def parse_record(self):
        """
        Parse one profile data record of the zplsc-c data file.
        """
        chan_values = [[], [], [], []]
        overflow_values = [[], [], [], []]

        # Parse the data values portion of the record.
        for chan in range(self.ph.num_channels):
            num_bins = self.ph.num_bins[chan]

            # Set the data structure format for the scientific data, based on whether
            # the data is averaged or not. Construct the data structure and read the
            # data bytes for the current channel. Unpack the data based on the structure.
            if self.ph.is_averaged_data[chan]:
                data_struct_format = '>' + str(num_bins) + 'I'
            else:
                data_struct_format = '>' + str(num_bins) + 'H'
            data_struct = struct.Struct(data_struct_format)
            data = self._stream_handle.read(data_struct.size)
            chan_values[chan] = data_struct.unpack(data)

            # If the data type is for averaged data, calculate the averaged data taking the
            # the linear sum channel values and overflow values and using calculations from
            # ASL MatLab code.
            if self.ph.is_averaged_data[chan]:
                overflow_struct_format = '>' + str(num_bins) + 'B'
                overflow_struct = struct.Struct(overflow_struct_format)
                overflow_data = self._stream_handle.read(num_bins)
                overflow_values[chan] = overflow_struct.unpack(overflow_data)

                if self.ph.is_averaged_pings:
                    divisor = self.ph.num_pings_profile * self.ph.range_samples[chan]
                else:
                    divisor = self.ph.range_samples[chan]

                linear_sum_values = np.array(chan_values[chan])
                linear_overflow_values = np.array(overflow_values[chan])

                values = (linear_sum_values + (linear_overflow_values * 0xFFFFFFFF))/divisor
                values = (np.log10(values) - 2.5) * (8*0xFFFF) * self.cc.DS[chan]
                values[np.isinf(values)] = 0
                chan_values[chan] = values

        # Convert the date and time parameters to a epoch time from 01-01-1900.
        timestamp = (datetime(self.ph.year, self.ph.month, self.ph.day,
                              self.ph.hour, self.ph.minute, self.ph.second,
                              (self.ph.hundredths * 10000)) - datetime(1900, 1, 1)).total_seconds()

        sound_speed, depth_range, sea_absorb = self.zplsc_echogram.compute_echogram_metadata(self.ph)

        chan_values = self.zplsc_echogram.compute_backscatter(self.ph, chan_values, sound_speed, depth_range,
                                                              sea_absorb)

        zplsc_particle_data = {
            ZplscCParticleKey.TRANS_TIMESTAMP: timestamp,
            ZplscCParticleKey.SERIAL_NUMBER: str(self.ph.serial_num),
            ZplscCParticleKey.PHASE: self.ph.phase,
            ZplscCParticleKey.BURST_NUMBER: self.ph.burst_num,
            ZplscCParticleKey.TILT_X: self.ph.tilt_x,
            ZplscCParticleKey.TILT_Y: self.ph.tilt_y,
            ZplscCParticleKey.BATTERY_VOLTAGE: self.ph.battery_voltage,
            ZplscCParticleKey.PRESSURE: self.ph.pressure,
            ZplscCParticleKey.TEMPERATURE: self.ph.temperature,
            ZplscCParticleKey.IS_AVERAGED_DATA: list(self.ph.is_averaged_data),
            ZplscCParticleKey.FREQ_CHAN_1: float(self.ph.frequency[0]),
            ZplscCParticleKey.VALS_CHAN_1: list(chan_values[0]),
            ZplscCParticleKey.DEPTH_CHAN_1: list(depth_range[0]),
            ZplscCParticleKey.FREQ_CHAN_2: float(self.ph.frequency[1]),
            ZplscCParticleKey.VALS_CHAN_2: list(chan_values[1]),
            ZplscCParticleKey.DEPTH_CHAN_2: list(depth_range[1]),
            ZplscCParticleKey.FREQ_CHAN_3: float(self.ph.frequency[2]),
            ZplscCParticleKey.VALS_CHAN_3: list(chan_values[2]),
            ZplscCParticleKey.DEPTH_CHAN_3: list(depth_range[2]),
            ZplscCParticleKey.FREQ_CHAN_4: float(self.ph.frequency[3]),
            ZplscCParticleKey.VALS_CHAN_4: list(chan_values[3]),
            ZplscCParticleKey.DEPTH_CHAN_4: list(depth_range[3])
        }

        return zplsc_particle_data, timestamp, chan_values, depth_range

    def parse_file(self):
        self.ph = AzfpProfileHeader()
        self.find_next_record()
        while self._stream_handle.readinto(self.ph):
            try:
                # Parse the current record
                zplsc_particle_data, timestamp, _, _ = self.parse_record()

                # Create the data particle
                particle = self._extract_sample(ZplscCRecoveredDataParticle, None, zplsc_particle_data, timestamp,
                                                timestamp, DataParticleKey.PORT_TIMESTAMP)
                if particle is not None:
                    log.trace('Parsed particle: %s' % particle.generate_dict())
                    self._record_buffer.append(particle)

            except (IOError, OSError) as ex:
                self._exception_callback('Reading stream handle: %s: %s\n' % (self._stream_handle.name, ex.message))
                return
            except struct.error as ex:
                self._exception_callback('Unpacking the data from the data structure: %s' % ex.message)
            except exceptions.ValueError as ex:
                self._exception_callback('Transition timestamp has invalid format: %s' % ex.message)
            except (SampleException, RecoverableSampleException) as ex:
                self._exception_callback('Creating data particle: %s' % ex.message)

            # Clear the profile header data structure and find the next record.
            self.ph = AzfpProfileHeader()
            self.find_next_record()

    def create_echogram(self, echogram_file_path=None):
        """
        Parse the *.O1A zplsc_c data file and create the echogram from this data.

        :param echogram_file_path: Path to store the echogram locally.
        :return:
        """

        sv_dict = {}
        data_times = []
        frequencies = {}
        depth_range = []

        input_file_path = self._stream_handle.name
        log.info('Begin processing echogram data: %r', input_file_path)
        image_path = generate_image_file_path(input_file_path, echogram_file_path)

        self.ph = AzfpProfileHeader()
        self.find_next_record()
        while self._stream_handle.readinto(self.ph):
            try:
                _, timestamp, chan_data, depth_range = self.parse_record()

                if not sv_dict:
                    range_chan_data = range(1, len(chan_data)+1)
                    sv_dict = {channel: [] for channel in range_chan_data}
                    frequencies = {channel: float(self.ph.frequency[channel-1]) for channel in range_chan_data}

                for channel in sv_dict:
                    sv_dict[channel].append(chan_data[channel-1])

                data_times.append(timestamp)

            except (IOError, OSError) as ex:
                self._exception_callback(ex)
                return
            except struct.error as ex:
                self._exception_callback(ex)
            except exceptions.ValueError as ex:
                self._exception_callback(ex)
            except (SampleException, RecoverableSampleException) as ex:
                self._exception_callback(ex)

            # Clear the profile header data structure and find the next record.
            self.ph = AzfpProfileHeader()
            self.find_next_record()

        log.info('Completed processing all data: %r', input_file_path)

        data_times = np.array(data_times)

        for channel in sv_dict:
            sv_dict[channel] = np.array(sv_dict[channel])

        log.info('Begin generating echogram: %r', image_path)

        plot = ZPLSPlot(data_times, sv_dict, frequencies, depth_range[0][-1], depth_range[0][0])
        plot.generate_plots()
        plot.write_image(image_path)

        log.info('Completed generating echogram: %r', image_path)
