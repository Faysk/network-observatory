import tempfile,unittest
from pathlib import Path
from tools.import_manuf import convert
from app.device_identity import OuiRegistry,inspect_mac

class ManufTests(unittest.TestCase):
    def test_source_and_local_mac_safety(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'manuf';source.write_text('# fixture\n00:11:22 Fixture Fixture Assignee\n02:11:22 Local Local Synthetic\n00:11:22:30:00:00/28 Narrow Narrow Fixture\n')
            text,count=convert(source);self.assertEqual(count,2)
            out=Path(folder)/'vendors.tsv';out.write_text(text)
            registry=OuiRegistry.from_file(out)
            result=inspect_mac('00:11:22:34:56:78',registry=registry)
            self.assertEqual(result['oui_vendor'],'Narrow Fixture');self.assertEqual(result['oui_source'],'wireshark_manuf')
            self.assertIsNone(inspect_mac('02:11:22:34:56:78',registry=registry)['oui_vendor'])
