"""Authored BYML/selection fixtures; no RomFS, extracted models or texture data."""
import argparse
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from coop_byml import read_byml
from prepare_coop_gear import select_actors, library_counts
from prepare_coop_figure import private_output


def fixture(endian='<'):
    order='little' if endian=='<' else 'big'
    def strings(values):
        start=4+4*(len(values)+1); offsets=[start]; raw=b''
        for value in values:
            raw+=value.encode()+b'\0'; offsets.append(start+len(raw))
        return b'\xc2'+len(values).to_bytes(3,order)+struct.pack(endian+f'{len(offsets)}I',*offsets)+raw
    keys=strings(['ModelProjectName','FmdbName']); values=strings(['Synthetic','Blade'])
    root=16+len(keys)+len(values)
    head=(b'YB' if endian=='<' else b'BY')+struct.pack(endian+'HIII',7,16,16+len(keys),root)
    entries=b''.join(i.to_bytes(3,order)+b'\xa0'+struct.pack(endian+'I',i) for i in range(2))
    return head+keys+values+b'\xc1'+(2).to_bytes(3,order)+entries


class PrepareChecks(unittest.TestCase):
    def test_byml_model_info_both_byte_orders(self):
        for endian in ('<','>'):
            data=fixture(endian)
            self.assertEqual(read_byml(data),dict(ModelProjectName='Synthetic',FmdbName='Blade'))
            for n in range(len(data)):
                with self.assertRaises(ValueError): read_byml(data[:n])

    def test_invalid_byml_indices_and_cycles(self):
        data=bytearray(fixture()); data[-4:]=struct.pack('<I',99)
        with self.assertRaises(ValueError): read_byml(data)
        # One array referring back to itself, without string tables.
        cycle=b'YB'+struct.pack('<HIII',7,0,0,16)+b'\xc0\x01\0\0\xc0\0\0\0'+struct.pack('<I',16)
        with self.assertRaises(ValueError): read_byml(cycle)
        huge=b'YB'+struct.pack('<HIII',7,0,0,16)+b'\xc0\xff\xff\xff'
        with self.assertRaises(ValueError): read_byml(huge)

    def test_selects_only_requested_equipment_and_preserves_model_aliases(self):
        available={'Weapon_Sword_101':'Synthetic.Blade','Weapon_Sword_102':'Synthetic.Blade',
                   'Weapon_Shield_005':'Synthetic.Shield','Weapon_Bow_004':'Synthetic.Bow'}
        chosen=select_actors(['Weapon_Sword_102','Weapon_Sword_101','Weapon_Sword_102'],available)
        self.assertEqual(len(chosen),2); self.assertEqual(len(set(chosen.values())),1)
        for requested in ([],['../Weapon_Sword_101'],['Weapon_Sword_999'],['Weapon_Sword_a']):
            with self.assertRaises(ValueError): select_actors(requested,available)
        with self.assertRaises(ValueError): select_actors(['Weapon_Sword_101'],{'Weapon_Sword_101':'../bad'})

    def test_outputs_are_private_and_missing_models_fail(self):
        self.assertTrue(private_output(ROOT/'build/assets/gear.bin').is_relative_to(ROOT/'build'))
        for path in (ROOT/'runtime/gear.bin',ROOT/'build',ROOT/'build/../gear.bin'):
            with self.assertRaises(argparse.ArgumentTypeError): private_output(path)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'gear.bin'
            head=b'LNKA'+struct.pack('<III',2,1,1)+b'\0'
            record=b'Weapon_Sword_101'.ljust(48,b'\0')+struct.pack('<i',0)+b'\0\0'
            model=b'Synthetic.Blade'.ljust(48,b'\0')+struct.pack('<5IH',1,1,8,0,4,1)+b'\x03mat'
            model+=bytes(12)+struct.pack('<8H',0,65535,0,0,0,0,0,0)+bytes(12+1+2+24)+b'fake'
            path.write_bytes(head+record+model)
            self.assertEqual(library_counts(path,1),(1,1))
            path.write_bytes(head+record)
            with self.assertRaises(ValueError): library_counts(path,1)
            path.write_bytes(head+record[:48]+struct.pack('<i',-1)+b'\0\0')
            with self.assertRaises(ValueError): library_counts(path,1)


if __name__=='__main__': unittest.main()
