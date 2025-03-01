#!/usr/bin/env python

import os
import unittest

from mi.core.log import get_logger
from mi.dataset.dataset_driver import ParticleDataHandler
from mi.dataset.driver.ctdpf_ckl.wfp_sio.ctdpf_ckl_wfp_sio_telemetered_driver import parse
from mi.dataset.driver.ctdpf_ckl.wfp_sio.resource import RESOURCE_PATH

__author__ = 'Jeff Roy'
log = get_logger()


class SampleTest(unittest.TestCase):
    def test_one(self):

        source_file_path = os.path.join(RESOURCE_PATH, 'node58p1_0.wc_wfp.dat')

        particle_data_handler = ParticleDataHandler()

        particle_data_handler = parse(None, source_file_path, particle_data_handler)

        log.debug("SAMPLES: %s", particle_data_handler._samples)
        log.debug("FAILURE: %s", particle_data_handler._failure)

        self.assertEquals(particle_data_handler._failure, False)


if __name__ == '__main__':
    test = SampleTest('test_one')
    test.test_one()
