"""
@package mi.dataset.parser.optaa_dj_cspp
@file marine-integrations/mi/dataset/parser/optaa_dj_cspp.py
@author Joe Padula
@brief Parser for the optaa_dj_cspp dataset driver. This parser extends CsppParser
    located in cspp_base.py.
Release notes:

Initial Release
"""

import numpy
import re

from mi.core.common import BaseEnum
from mi.core.exceptions import RecoverableSampleException
from mi.core.instrument.dataset_data_particle import DataParticle
from mi.core.log import get_logger
from mi.dataset.parser.common_regexes import \
    END_OF_LINE_REGEX, \
    FLOAT_REGEX, \
    INT_REGEX

from mi.dataset.parser.cspp_base import \
    CsppParser, \
    HEADER_PART_MATCHER, \
    Y_OR_N_REGEX, \
    CsppMetadataDataParticle, \
    MetadataRawDataKey, \
    encode_y_or_n

log = get_logger()

__author__ = 'Joe Padula'
__license__ = 'Apache 2.0'

TAB_REGEX = r'\t'
# This is the beginning part of the REGEX, the rest of it varies
BEGIN_REGEX = '(' + FLOAT_REGEX + ')' + TAB_REGEX     # Profiler Timestamp
BEGIN_REGEX += '(' + FLOAT_REGEX + ')' + TAB_REGEX    # Depth
BEGIN_REGEX += '(' + Y_OR_N_REGEX + ')' + TAB_REGEX   # Suspect Timestamp
BEGIN_REGEX += '(' + INT_REGEX + ')' + TAB_REGEX      # serial number
BEGIN_REGEX += '(' + FLOAT_REGEX + ')' + TAB_REGEX    # powered on seconds
BEGIN_REGEX += '(' + INT_REGEX + ')' + TAB_REGEX      # num wavelengths
BEGIN_MATCHER = re.compile(BEGIN_REGEX)


class DataMatchesGroupNumber(BaseEnum):
    """
    An enum for group match indices for a data record chunk.
    These indices are into match.group(INDEX).
    Used to access the match groups in the particle raw data
    """
    PROFILER_TIMESTAMP = 1
    DEPTH = 2
    SUSPECT_TIMESTAMP = 3
    SERIAL_NUMBER = 4
    ON_SECONDS = 5
    NUM_WAVELENGTHS = 6
    C_REF_DARK = 7
    C_REF_COUNTS = 8
    C_SIG_DARK = 9
    C_SIG_COUNTS = 10
    A_REF_DARK = 11
    A_REF_COUNTS = 12
    A_SIG_DARK = 13
    A_SIG_COUNTS = 14
    EXTERNAL_TEMP_COUNTS = 15
    INTERNAL_TEMP_COUNTS = 16
    PRESSURE_COUNTS = 17


class DataParticleType(BaseEnum):
    """
    The data particle types that this parser can generate
    """
    METADATA_RECOVERED = 'optaa_dj_cspp_metadata_recovered'
    INSTRUMENT_RECOVERED = 'optaa_dj_cspp_instrument_recovered'
    METADATA_TELEMETERED = 'optaa_dj_cspp_metadata'
    INSTRUMENT_TELEMETERED = 'optaa_dj_cspp_instrument'


class OptaaDjCsppParserDataParticleKey(BaseEnum):

    """
    The data particle keys associated with the metadata particle parameters
    """
    # non-common metadata particle key
    SERIAL_NUMBER = 'serial_number'

    # The data particle keys associated with the data instrument particle parameters
    PROFILER_TIMESTAMP = 'profiler_timestamp'
    PRESSURE_DEPTH = 'pressure_depth'
    SUSPECT_TIMESTAMP = 'suspect_timestamp'
    ON_SECONDS = 'on_seconds'
    NUM_WAVELENGTHS = 'num_wavelengths'
    C_REFERENCE_DARK_COUNTS = 'c_reference_dark_counts'
    C_REFERENCE_COUNTS = 'c_reference_counts'
    C_SIGNAL_DARK_COUNTS = 'c_signal_dark_counts'
    C_SIGNAL_COUNTS = 'c_signal_counts'
    A_REFERENCE_DARK_COUNTS = 'a_reference_dark_counts'
    A_REFERENCE_COUNTS = 'a_reference_counts'
    A_SIGNAL_DARK_COUNTS = 'a_signal_dark_counts'
    A_SIGNAL_COUNTS = 'a_signal_counts'
    EXTERNAL_TEMP_RAW = 'external_temp_raw'
    INTERNAL_TEMP_RAW = 'internal_temp_raw'
    PRESSURE_COUNTS = 'pressure_counts'

# Two groups instrument particle encoding rules used to simplify encoding using a loop.

# This the beginning part of the encoding, before the lists.
INSTRUMENT_PARTICLE_ENCODING_RULES_BEGIN = [
    # Since 1/1/70 with millisecond resolution
    (OptaaDjCsppParserDataParticleKey.PROFILER_TIMESTAMP, DataMatchesGroupNumber.PROFILER_TIMESTAMP, numpy.float),
    # "Depth" from Record Structure section
    (OptaaDjCsppParserDataParticleKey.PRESSURE_DEPTH, DataMatchesGroupNumber.DEPTH, float),
    # Flag indicating a potential inaccuracy in the timestamp
    (OptaaDjCsppParserDataParticleKey.SUSPECT_TIMESTAMP, DataMatchesGroupNumber.SUSPECT_TIMESTAMP, encode_y_or_n),
    # Powered On Seconds
    (OptaaDjCsppParserDataParticleKey.ON_SECONDS, DataMatchesGroupNumber.ON_SECONDS, float),
    # Number of output wavelengths.
    (OptaaDjCsppParserDataParticleKey.NUM_WAVELENGTHS, DataMatchesGroupNumber.NUM_WAVELENGTHS, int)
]

# This the end part of the encoding, after the lists.
INSTRUMENT_PARTICLE_ENCODING_RULES_END = [
    # Temperature external to the instrument measured in counts.
    (OptaaDjCsppParserDataParticleKey.EXTERNAL_TEMP_RAW, DataMatchesGroupNumber.EXTERNAL_TEMP_COUNTS, int),
    # Temperature internal to the instrument measured in counts.
    (OptaaDjCsppParserDataParticleKey.INTERNAL_TEMP_RAW, DataMatchesGroupNumber.INTERNAL_TEMP_COUNTS, int),
    # Raw A/D counts from the pressure sensor
    (OptaaDjCsppParserDataParticleKey.PRESSURE_COUNTS, DataMatchesGroupNumber.PRESSURE_COUNTS, int)
]


class OptaaDjCsppMetadataDataParticle(CsppMetadataDataParticle):
    """
    Base Class for building a metadata particle
    """

    def _build_parsed_values(self):
        """
        Take something in the data format and turn it into
        an array of dictionaries defining the data in the particle
        with the appropriate tag.
        @returns results a list of encoded metadata particle (key/value pairs)
        @throws RecoverableSampleException If there is a problem with sample creation
        """
        metadata_particle = []

        # Call base class to append the base metadata parsed values to the particle to return
        metadata_particle += self._build_metadata_parsed_values()

        data_match = self.raw_data[MetadataRawDataKey.DATA_MATCH]

        # Process the non common metadata particle parameter

        # Instrument serial number (from first record)
        metadata_particle.append(self._encode_value(OptaaDjCsppParserDataParticleKey.SERIAL_NUMBER,
                                                    data_match.group(DataMatchesGroupNumber.SERIAL_NUMBER),
                                                    str))

        # Set the internal timestamp
        internal_timestamp_unix = numpy.float(data_match.group(
            DataMatchesGroupNumber.PROFILER_TIMESTAMP))
        self.set_internal_timestamp(unix_time=internal_timestamp_unix)

        return metadata_particle


class OptaaDjCsppMetadataRecoveredDataParticle(OptaaDjCsppMetadataDataParticle):
    """
    Class for building a recovered metadata particle
    """

    _data_particle_type = DataParticleType.METADATA_RECOVERED


class OptaaDjCsppMetadataTelemeteredDataParticle(OptaaDjCsppMetadataDataParticle):
    """
    Class for building a telemetered metadata particle
    """

    _data_particle_type = DataParticleType.METADATA_TELEMETERED


class OptaaDjCsppInstrumentDataParticle(DataParticle):
    """
    Base Class for building a instrument data particle
    """

    def _build_parsed_values(self):
        """
        Take something in the data format and turn it into
        an array of dictionaries defining the data in the particle
        with the appropriate tag.
        @throws RecoverableSampleException If there is a problem with sample creation
        """

        results = []

        # Process each of the non-list type instrument particle parameters that occur first
        for name, group, function in INSTRUMENT_PARTICLE_ENCODING_RULES_BEGIN:
            results.append(self._encode_value(name, self.raw_data.group(group), function))

        # The following is a mix if int, followed by a list.

        # C-channel reference dark counts, used for diagnostic purposes.
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.C_REFERENCE_DARK_COUNTS,
                                          self.raw_data.group(DataMatchesGroupNumber.C_REF_DARK),
                                          int))

        # Array of raw c-channel reference counts
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.C_REFERENCE_COUNTS,
                                          self._build_list_for_encoding(DataMatchesGroupNumber.C_REF_COUNTS),
                                          list))

        # C-signal reference dark counts, used for diagnostic purposes.
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.C_SIGNAL_DARK_COUNTS,
                                          self.raw_data.group(DataMatchesGroupNumber.C_SIG_DARK),
                                          int))

        # Array of raw c-channel signal counts
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.C_SIGNAL_COUNTS,
                                          self._build_list_for_encoding(DataMatchesGroupNumber.C_SIG_COUNTS),
                                          list))

        # A-channel reference dark counts, used for diagnostic purposes.
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.A_REFERENCE_DARK_COUNTS,
                                          self.raw_data.group(DataMatchesGroupNumber.A_REF_DARK),
                                          int))

        # Array of raw a-channel reference counts
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.A_REFERENCE_COUNTS,
                                          self._build_list_for_encoding(DataMatchesGroupNumber.A_REF_COUNTS),
                                          list))

        # A-signal reference dark counts, used for diagnostic purposes.
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.A_SIGNAL_DARK_COUNTS,
                                          self.raw_data.group(DataMatchesGroupNumber.A_SIG_DARK),
                                          int))

        # Array of raw a-channel signal counts
        results.append(self._encode_value(OptaaDjCsppParserDataParticleKey.A_SIGNAL_COUNTS,
                                          self._build_list_for_encoding(DataMatchesGroupNumber.A_SIG_COUNTS),
                                          list))

        # Process each of the non-list instrument particle parameters that occur last
        for name, group, function in INSTRUMENT_PARTICLE_ENCODING_RULES_END:
            results.append(self._encode_value(name, self.raw_data.group(group), function))

        # Set the internal timestamp
        internal_timestamp_unix = numpy.float(self.raw_data.group(
                                              DataMatchesGroupNumber.PROFILER_TIMESTAMP))
        self.set_internal_timestamp(unix_time=internal_timestamp_unix)

        return results

    def _build_list_for_encoding(self, group_num):
        """
        Helper method for building the list that is needed for encoding
        @param group_num the group number of the match
        @return the list of counts
        """

        # Load the tab separated string
        tab_str = self.raw_data.group(group_num)
        # Strip off the ending tab
        tab_str_stripped = tab_str.strip('\t')
        counts_list = tab_str_stripped.split('\t')

        # return a list of integers
        return map(int, counts_list)


class OptaaDjCsppInstrumentRecoveredDataParticle(OptaaDjCsppInstrumentDataParticle):
    """
    Class for building a recovered instrument data particle
    """

    _data_particle_type = DataParticleType.INSTRUMENT_RECOVERED


class OptaaDjCsppInstrumentTelemeteredDataParticle(OptaaDjCsppInstrumentDataParticle):
    """
    Class for building a telemetered instrument data particle
    """

    _data_particle_type = DataParticleType.INSTRUMENT_TELEMETERED


class OptaaDjCsppParser(CsppParser):

    def __init__(self,
                 config,
                 stream_handle,
                 exception_callback):
        """
        This method is a constructor that will instantiate an OptaaDjCsppParser object.
        @param config The configuration for this OptaaDjCsppParser parser
        @param stream_handle The handle to the data stream containing the optaa_dj_cspp data
        @param exception_callback The function to call to report exceptions
        """

        # Call the superclass constructor
        super(OptaaDjCsppParser, self).__init__(config,
                                                stream_handle,
                                                exception_callback,
                                                BEGIN_REGEX)

    @staticmethod
    def _build_data_regex(regex, count):
        """
        Helper method for building up regex
        @param regex the beginning part of the regex that has already been determined
        @param count the number of items in the array
        """

        data_regex = regex
        array = r'((?:\d+\t){%s})' % count

        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # C Ref Dark
        data_regex += array                                 # C Ref Counts

        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # C Sig Dark
        data_regex += array                                 # C Sig Counts

        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # A Ref Dark
        data_regex += array                                 # A Ref Counts

        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # A Sig Dark
        data_regex += array                                 # A Sig Counts

        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # External Temp Counts
        data_regex += '(' + INT_REGEX + ')' + TAB_REGEX     # Internal Temp Counts
        data_regex += '(' + INT_REGEX + ')'                 # Pressure Counts

        data_regex += r'\t*' + END_OF_LINE_REGEX

        return data_regex

    def parse_file(self):
        """
        Parse through the file, pulling single lines and comparing to the established patterns,
        generating particles for data lines
        """

        for line in self._stream_handle:

            match = BEGIN_MATCHER.match(line)

            if match is not None:

                count = match.group(DataMatchesGroupNumber.NUM_WAVELENGTHS)

                data_regex = self._build_data_regex(BEGIN_REGEX, count)

                fields = re.match(data_regex, line)

                if fields is not None:
                    self._process_data_match(fields, self._record_buffer)
                else:  # did not match the regex
                    log.warn("line did not match regex %s", line)
                    self._exception_callback(RecoverableSampleException("Found an invalid line: %s" % line))

            else:
                # Check for head part match
                header_part_match = HEADER_PART_MATCHER.match(line)

                if header_part_match is not None:
                    self._process_header_part_match(header_part_match)
                else:
                    self._process_line_not_containing_data_record_or_header_part(line)
