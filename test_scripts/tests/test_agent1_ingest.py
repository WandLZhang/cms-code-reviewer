import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add the function directory to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../1_graph_creation/functions/agent1_ingest_source')))

from main import ingest_source

class TestAgent1Ingest(unittest.TestCase):

    def setUp(self):
        self.mock_request = MagicMock()
        self.mock_request.method = 'POST'

    def test_ingest_direct_content_success(self):
        """Test successful ingestion with direct content."""
        cobol_code = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTPROG.
       PROCEDURE DIVISION.
           DISPLAY 'HELLO WORLD'.
           GOBACK.
        """
        self.mock_request.get_json.return_value = {
            "content": cobol_code,
            "filename": "test_prog.cbl"
        }
        
        # Run function
        response = ingest_source(self.mock_request)
        
        # Verify
        self.assertEqual(response[1], 200)
        data = response[0].get_json()
        self.assertEqual(data['program_id'], 'TESTPROG')
        self.assertEqual(data['node']['properties']['program_id'], 'TESTPROG')
        self.assertEqual(data['node']['properties']['status'], 'INGESTED')

    def test_ingest_no_program_id_fallback(self):
        """Test fallback to filename when PROGRAM-ID is missing."""
        cobol_code = """
       IDENTIFICATION DIVISION.
       * No program ID here
        """
        self.mock_request.get_json.return_value = {
            "content": cobol_code,
            "filename": "FALLBACK.cbl"
        }

        response = ingest_source(self.mock_request)
        
        self.assertEqual(response[1], 200)
        data = response[0].get_json()
        self.assertEqual(data['program_id'], 'FALLBACK')

    @patch('main.storage.Client')
    def test_ingest_gcs_content_success(self, mock_storage_client):
        """Test successful ingestion from GCS."""
        cobol_code = """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GCSPROG.
        """
        
        # Mock GCS interactions
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_text.return_value = cobol_code
        mock_bucket.blob.return_value = mock_blob
        mock_storage_client.return_value.bucket.return_value = mock_bucket

        self.mock_request.get_json.return_value = {
            "gcs_uri": "gs://my-bucket/folder/GCSPROG.cbl"
        }

        response = ingest_source(self.mock_request)

        self.assertEqual(response[1], 200)
        data = response[0].get_json()
        self.assertEqual(data['program_id'], 'GCSPROG')
        
        # Verify GCS calls
        mock_storage_client.return_value.bucket.assert_called_with('my-bucket')
        mock_bucket.blob.assert_called_with('folder/GCSPROG.cbl')

    def test_missing_inputs(self):
        """Test error when no content or GCS URI is provided."""
        self.mock_request.get_json.return_value = {
            "other_field": "value"
        }

        response = ingest_source(self.mock_request)
        
        self.assertEqual(response[1], 400)
        self.assertIn('error', response[0].get_json())

    @patch('main.requests.post')
    @patch.dict(os.environ, {'AGENT2_URL': 'http://agent2'})
    def test_forward_to_agent2(self, mock_post):
        """Test that Agent 2 is called if URL is present."""
        # Note: In the actual code, this happens in a thread.
        # Testing threaded code in unit tests can be tricky.
        # We might mock threading.Thread to execute immediately or check call args.
        
        with patch('main.threading.Thread') as mock_thread:
            cobol_code = "PROGRAM-ID. FWDPROG."
            self.mock_request.get_json.return_value = {
                "content": cobol_code,
                "filename": "FWDPROG.cbl"
            }

            ingest_source(self.mock_request)

            self.assertTrue(mock_thread.called)
            args, _ = mock_thread.call_args
            # target = args[0], args = args[1] in Thread(target=..., args=...) constructor?
            # Thread(target=send_to_agent2, args=(agent2_url, payload))
            # The mock call_args depends on how it was called. 
            # It was called with keywords: target=..., args=...
            
            _, kwargs = mock_thread.call_args
            self.assertEqual(kwargs['args'][0], 'http://agent2')
            self.assertEqual(kwargs['args'][1]['program_id'], 'FWDPROG')

if __name__ == '__main__':
    unittest.main()
