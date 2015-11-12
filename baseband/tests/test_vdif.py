import io
import os
import numpy as np
from astropy.tests.helper import pytest
from .. import vdif, vlbi_base


SAMPLE_FILE = os.path.join(os.path.dirname(__file__), 'sample.vdif')


# Comparisn with m5access routines (check code on 2015-MAY-30) on vlba.m5a,
# which contains the first 16 frames from evn/Fd/GP052D_FD_No0006.m5a.
# 00000000  77 2c db 00 00 00 00 1c  75 02 00 20 fc ff 01 04  # header 0 - 3
# 00000010  10 00 80 03 ed fe ab ac  00 00 40 33 83 15 03 f2  # header 4 - 7
# 00000020  2a 0a 7c 43 8b 69 9d 59  cb 99 6d 9a 99 96 5d 67  # data 0 - 3
# NOTE: thread_id = 1
# 2a = 00 10 10 10 = (lsb first) 1,  1,  1, -3
# 0a = 00 00 10 10 =             1,  1, -3, -3
# 7c = 01 11 11 00 =            -3,  3,  3, -1
# m5d evn/Fd/GP052D_FD_No0006.m5a VDIF_5000-512-1-2 100
# Mark5 stream: 0x16cd140
#   stream = File-1/1=evn/Fd/GP052D_FD_No0006.m5a
#   format = VDIF_5000-512-1-2 = 3
#   start mjd/sec = 56824 21367.000000000
#   frame duration = 78125.00 ns
#   framenum = 0
#   sample rate = 256000000 Hz
#   offset = 0
#   framebytes = 5032 bytes
#   datasize = 5000 bytes
#   sample granularity = 4
#   frame granularity = 1
#   gframens = 78125
#   payload offset = 32
#   read position = 0
#   data window size = 1048576 bytes


class TestVDIF(object):
    def test_header(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            header = vdif.VDIFHeader.fromfile(fh)
        assert header.size == 32
        assert header.edv == 3
        mjd, frac = divmod(header.time.mjd, 1)
        assert mjd == 56824
        assert round(frac * 86400) == 21367
        assert header.payloadsize == 5000
        assert header.framesize == 5032
        assert header['thread_id'] == 1
        assert header.framerate.value == 1600
        assert header.samples_per_frame == 20000
        assert header.nchan == 1
        assert header.bps == 2
        assert not header['complex_data']
        assert header.mutable is False
        with io.BytesIO() as s:
            header.tofile(s)
            s.seek(0)
            header2 = vdif.VDIFHeader.fromfile(s)
        assert header2 == header
        assert header2.mutable is False
        header3 = vdif.VDIFHeader.fromkeys(**header)
        assert header3 == header
        assert header3.mutable is True
        with pytest.raises(KeyError):
            vdif.VDIFHeader.fromkeys(extra=1, **header)
        with pytest.raises(KeyError):
            kwargs = dict(header)
            kwargs.pop('thread_id')
            vdif.VDIFHeader.fromkeys(**kwargs)
        # Try initialising with properties instead of keywords, as much as
        # possible.  Note that we still have to give a lots of extra, less
        # directly useful parameters to get an *identical* header.
        header4 = vdif.VDIFHeader.fromvalues(
            edv=header.edv, time=header.time,
            samples_per_frame=header.samples_per_frame,
            station=header.station, bandwidth=header.bandwidth,
            bps=header.bps, complex_data=header['complex_data'],
            thread_id=header['thread_id'],
            loif_tuning=header['loif_tuning'], dbe_unit=header['dbe_unit'],
            if_nr=header['if_nr'], subband=header['subband'],
            sideband=header['sideband'], major_rev=header['major_rev'],
            minor_rev=header['minor_rev'], personality=header['personality'],
            _7_28_4=header['_7_28_4'])
        assert header4 == header
        assert header4.mutable is True
        header5 = header.copy()
        assert header5 == header
        assert header5.mutable is True
        header5['thread_id'] = header['thread_id'] + 1
        assert header5['thread_id'] == header['thread_id'] + 1
        assert header5 != header
        with pytest.raises(TypeError):
            header['thread_id'] = 0

    def test_decoding(self):
        """Check that look-up levels are consistent with mark5access."""
        o2h = vlbi_base.payload.OPTIMAL_2BIT_HIGH
        assert np.all(vdif.payload.lut1bit[0] == -1.)
        assert np.all(vdif.payload.lut1bit[0xff] == 1.)
        assert np.all(vdif.payload.lut1bit.astype(int) ==
                      ((np.arange(256)[:, np.newaxis] >>
                        np.arange(8)) & 1) * 2 - 1)
        assert np.all(vdif.payload.lut2bit[0] == -o2h)
        assert np.all(vdif.payload.lut2bit[0x55] == -1.)
        assert np.all(vdif.payload.lut2bit[0xaa] == 1.)
        assert np.all(vdif.payload.lut2bit[0xff] == o2h)
        assert np.all(vdif.payload.lut4bit[0] * 2.95 == -8.)
        assert np.all(vdif.payload.lut4bit[0x88] == 0.)
        assert np.all(vdif.payload.lut4bit[0xff] * 2.95 == 7)
        assert np.all(-vdif.payload.lut4bit[0x11] ==
                      vdif.payload.lut4bit[0xff])

    def test_payload(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            header = vdif.VDIFHeader.fromfile(fh)
            payload = vdif.VDIFPayload.fromfile(fh, header)
        assert payload.size == 5000
        assert payload.shape == (20000, 1)
        assert payload.dtype == np.float32
        assert np.all(payload.data[:12, 0].astype(int) ==
                      np.array([1, 1, 1, -3, 1, 1, -3, -3, -3, 3, 3, -1]))
        with io.BytesIO() as s:
            payload.tofile(s)
            s.seek(0)
            payload2 = vdif.VDIFPayload.fromfile(s, header)
            assert payload2 == payload
            with pytest.raises(EOFError):
                # Too few bytes.
                s.seek(100)
                vdif.VDIFPayload.fromfile(s, header)
        payload3 = vdif.VDIFPayload.fromdata(payload.data, header)
        assert payload3 == payload
        with pytest.raises(ValueError):
            # Wrong number of channels.
            vdif.VDIFPayload.fromdata(np.empty((payload.shape[0], 2)), header)
        with pytest.raises(ValueError):
            # Too few data.
            vdif.VDIFPayload.fromdata(payload.data[:100], header)

    def test_frame(self):
        with vdif.open(SAMPLE_FILE, 'rb') as fh:
            header = vdif.VDIFHeader.fromfile(fh)
            payload = vdif.VDIFPayload.fromfile(fh, header)
            fh.seek(0)
            frame = fh.read_frame()

        assert frame.header == header
        assert frame.payload == payload
        assert frame == vdif.VDIFFrame(header, payload)
        assert np.all(frame.data[:12, 0].astype(int) ==
                      np.array([1, 1, 1, -3, 1, 1, -3, -3, -3, 3, 3, -1]))
        with io.BytesIO() as s:
            frame.tofile(s)
            s.seek(0)
            frame2 = vdif.VDIFFrame.fromfile(s)
        assert frame2 == frame
        frame3 = vdif.VDIFFrame.fromdata(payload.data, header)
        assert frame3 == frame
        frame4 = vdif.VDIFFrame.fromdata(payload.data, **header)
        assert frame4 == frame
        header5 = header.copy()
        frame5 = vdif.VDIFFrame(header5, payload, valid=False)
        assert frame5.valid is False
        assert np.all(frame5.data == 0.)
        frame5.valid = True
        assert frame5 == frame

    def test_frameset(self):
        with vdif.open(SAMPLE_FILE, 'rb') as fh:
            header = vdif.VDIFHeader.fromfile(fh)
            fh.seek(0)
            frameset = fh.read_frameset()

        assert len(frameset.frames) == 8
        assert frameset.samples_per_frame == 20000
        assert frameset.nchan == 1
        assert frameset.shape == (8, 20000, 1)
        assert frameset.size == 8 * frameset.frames[0].size
        assert 'edv' in frameset
        assert 'edv' in frameset.keys()
        assert frameset['edv'] == 3
        # Properties from headers are passed on if they are settable.
        assert frameset.time == frameset.header0.time
        with pytest.raises(AttributeError):
            # But not all.
            frameset.update(1)
        assert ([fr.header['thread_id'] for fr in frameset.frames] ==
                list(range(8)))
        first_frame = frameset.frames[header['thread_id']]
        assert first_frame.header == header
        assert np.all(first_frame.data[:12, 0].astype(int) ==
                      np.array([1, 1, 1, -3, 1, 1, -3, -3, -3, 3, 3, -1]))
        assert np.all(frameset.frames[0].data[:12, 0].astype(int) ==
                      np.array([-1, -1, 3, -1, 1, -1, 3, -1, 1, 3, -1, 1]))
        assert np.all(frameset.frames[3].data[:12, 0].astype(int) ==
                      np.array([-1, 1, -1, 1, -3, -1, 3, -1, 3, -3, 1, 3]))

        with vdif.open(SAMPLE_FILE, 'rb') as fh:
            frameset2 = fh.read_frameset(thread_ids=[2, 3])
        assert frameset2.shape == (2, 20000, 1)
        assert np.all(frameset2.data == frameset.data[2:4])

        frameset3 = vdif.VDIFFrameSet(frameset.frames, frameset.header0)
        assert frameset3 == frameset
        frameset4 = vdif.VDIFFrameSet.fromdata(frameset.data, frameset.header0)
        assert np.all(frameset4.data == frameset.data)
        assert frameset4.time == frameset.time
        # the following check cannot be done with frameset itself, since
        # the times in four of the eight headers are wrong.
        frameset5 = vdif.VDIFFrameSet.fromdata(frameset.data,
                                               frameset4.header0)
        assert frameset5 == frameset4
        frameset6 = vdif.VDIFFrameSet.fromdata(frameset.data,
                                               **frameset4.header0)
        assert frameset6 == frameset4

        with vdif.open(SAMPLE_FILE, 'rb') as fh:
            fh.seek(0)
            # try reading just a few threads
            frameset4 = fh.read_frameset(thread_ids=[2, 3])
            assert frameset4.header0.time == frameset.header0.time
            assert np.all(frameset.data[2:4] == frameset4.data)
            # Read beyond end
            fh.seek(-10064, 2)
            with pytest.raises(EOFError):
                fh.read_frameset(thread_ids=list(range(8)))
            # Give non-existent thread_id
            fh.seek(0)
            with pytest.raises(IOError):
                fh.read_frameset(thread_ids=[1, 9])

    def test_filestreamer(self):
        with open(SAMPLE_FILE, 'rb') as fh:
            header = vdif.VDIFHeader.fromfile(fh)

        with vdif.open(SAMPLE_FILE, 'rs') as fh:
            assert fh.readable() is True
            assert fh.writable() is False
            assert fh.seekable() is True
            assert fh.closed is False
            assert repr(fh).startswith('<VDIFStreamReader')
            assert fh.tell() == 0
            assert header == fh.header0
            record = fh.read(12)
            assert fh.tell() == 12
            fh.seek(10, 1)
            fh.tell() == 22
            fh.seek(0)
            assert fh.tell() == 0

        assert record.shape == (12, 8)
        assert np.all(record.astype(int)[:, 0] ==
                      np.array([-1, -1, 3, -1, 1, -1, 3, -1, 1, 3, -1, 1]))
