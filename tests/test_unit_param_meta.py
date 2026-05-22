"""Tests for backend/param_meta.py — XML parsing and metadata structure."""
from backend.param_meta import _parse_xml

SAMPLE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<paramfile>
  <parameters name="COPTER">
    <param name="ANGLE_MAX" humanName="Maximum Lean Angle" documentation="Maximum lean angle in all flight modes">
      <field name="Range">0 8000</field>
      <field name="Units">cdeg</field>
      <field name="Increment">10</field>
      <field name="Default">3000</field>
      <value code="0">Disabled</value>
      <value code="3000">30 degrees</value>
    </param>
    <param name="BATT_ARM_VOLT" humanName="Battery Arming Voltage" documentation="Minimum voltage to arm">
      <field name="Range">0 100</field>
      <field name="Units">V</field>
    </param>
    <param name="LOG_BITMASK" humanName="Log Bitmask" documentation="Controls which log types are enabled">
      <field name="Bitmask">0:Attitude,1:GPS,2:PM</field>
    </param>
  </parameters>
</paramfile>
"""


class TestParseXml:
    def test_parses_params(self):
        meta = _parse_xml(SAMPLE_XML)
        assert 'ANGLE_MAX' in meta
        assert 'BATT_ARM_VOLT' in meta
        assert 'LOG_BITMASK' in meta

    def test_range_field(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['range'] == [0.0, 8000.0]
        assert meta['BATT_ARM_VOLT']['range'] == [0.0, 100.0]

    def test_units_field(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['units'] == 'cdeg'
        assert meta['BATT_ARM_VOLT']['units'] == 'V'

    def test_increment_field(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['step'] == 10.0

    def test_default_field(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['default'] == 3000.0

    def test_values(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['values']['0'] == 'Disabled'
        assert meta['ANGLE_MAX']['values']['3000'] == '30 degrees'

    def test_bitmask(self):
        meta = _parse_xml(SAMPLE_XML)
        bm = meta['LOG_BITMASK']['bitmask']
        assert bm['0'] == 'Attitude'
        assert bm['1'] == 'GPS'
        assert bm['2'] == 'PM'

    def test_human_name(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['human'] == 'Maximum Lean Angle'

    def test_description(self):
        meta = _parse_xml(SAMPLE_XML)
        assert 'lean angle' in meta['ANGLE_MAX']['desc'].lower()

    def test_group(self):
        meta = _parse_xml(SAMPLE_XML)
        assert meta['ANGLE_MAX']['group'] == 'COPTER'

    def test_empty_xml(self):
        meta = _parse_xml(b'<paramfile></paramfile>')
        assert meta == {}

    def test_param_without_name_skipped(self):
        xml = b'<paramfile><parameters name="X"><param documentation="no name"></param></parameters></paramfile>'
        meta = _parse_xml(xml)
        assert meta == {}
