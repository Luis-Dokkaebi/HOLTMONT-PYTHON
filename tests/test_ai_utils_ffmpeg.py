import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure api module can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# We need to handle the conditional import in api.ai_utils
# Since we want to test the path where ffmpeg is available, we need to ensure it's not None
# But if it is None (because import failed), we can't patch it directly via 'api.ai_utils.ffmpeg' easily if it's None.
# However, we can patch `sys.modules` or use `patch.dict`.

# Let's try to patch `api.ai_utils.ffmpeg` assuming it might be None or module.
# If it is None, we need to patch the module attribute.

from api import ai_utils

class TestAIUtilsFFmpeg(unittest.TestCase):

    def setUp(self):
        # Ensure ai_utils.ffmpeg is treated as a mock for these tests
        pass

    @patch('api.ai_utils.Groq')
    def test_transcribir_audio_uses_ffmpeg(self, mock_groq):
        # We need to manually inject a mock for ffmpeg into api.ai_utils
        mock_ffmpeg = MagicMock()

        # Setup mocks for ffmpeg chain
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b'converted_audio', b'')
        mock_process.returncode = 0

        mock_input = MagicMock()
        mock_output = MagicMock()

        mock_ffmpeg.input.return_value = mock_input
        mock_input.output.return_value = mock_output
        mock_output.run_async.return_value = mock_process

        # Inject mock
        with patch.object(ai_utils, 'ffmpeg', mock_ffmpeg):
            # Mock Groq
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            mock_client.audio.transcriptions.create.return_value.text = "Transcription"

            # Call function
            api_key = "dummy_key"
            audio_content = b'original_audio'
            transcription = ai_utils.transcribir_audio(api_key, audio_content)

            # Verify ffmpeg was called
            mock_ffmpeg.input.assert_called_with('pipe:0')

            # Verify Groq was called with converted content
            mock_client.audio.transcriptions.create.assert_called()
            call_args = mock_client.audio.transcriptions.create.call_args
            # file arg is (filename, content)
            file_arg = call_args[1]['file']
            self.assertEqual(file_arg[1], b'converted_audio')
            self.assertEqual(file_arg[0], "converted_audio.wav")

    @patch('api.ai_utils.Groq')
    def test_transcribir_audio_fallback_on_ffmpeg_error(self, mock_groq):
        mock_ffmpeg = MagicMock()
        # Setup mock to raise exception
        mock_ffmpeg.input.side_effect = Exception("FFmpeg error")

        with patch.object(ai_utils, 'ffmpeg', mock_ffmpeg):
            # Mock Groq
            mock_client = MagicMock()
            mock_groq.return_value = mock_client
            mock_client.audio.transcriptions.create.return_value.text = "Transcription"

            # Call function
            api_key = "dummy_key"
            audio_content = b'original_audio'
            transcription = ai_utils.transcribir_audio(api_key, audio_content)

            # Verify Groq was called with original content
            mock_client.audio.transcriptions.create.assert_called()
            call_args = mock_client.audio.transcriptions.create.call_args
            file_arg = call_args[1]['file']
            self.assertEqual(file_arg[1], b'original_audio')
            self.assertEqual(file_arg[0], "audio.wav")

if __name__ == '__main__':
    unittest.main()
