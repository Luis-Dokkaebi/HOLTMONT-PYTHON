import re
import os
import unittest

class TestWorkOrderTemplate(unittest.TestCase):
    def test_dictation_buttons_implementation(self):
        """
        Verifies that dictation buttons in workorder_form.html use the correct
        toggleDictation(obj, key) syntax and isDictating(obj, key) class binding.
        """
        filepath = 'workorder_form.html'
        if not os.path.exists(filepath):
            self.fail(f"{filepath} not found.")

        with open(filepath, 'r') as f:
            content = f.read()

        # 1. Verify Main Description Button
        # It should call toggleDictation(workorderData, 'conceptoDesc')
        main_desc_click = r'toggleDictation\(workorderData,\s*\'conceptoDesc\'\)'
        self.assertTrue(re.search(main_desc_click, content),
                        "Main description button missing correct toggleDictation call.")

        # It should use isDictating(workorderData, 'conceptoDesc')
        main_desc_class = r'isDictating\(workorderData,\s*\'conceptoDesc\'\)'
        self.assertTrue(re.search(main_desc_class, content),
                        "Main description button missing correct isDictating class binding.")

        # 2. Verify Item Description Buttons (in loop)
        # It should call toggleDictation(item, 'description')
        item_desc_click = r'toggleDictation\(item,\s*\'description\'\)'
        self.assertTrue(re.search(item_desc_click, content),
                        "Item description buttons missing correct toggleDictation call.")

        # It should use isDictating(item, 'description')
        item_desc_class = r'isDictating\(item,\s*\'description\'\)'
        self.assertTrue(re.search(item_desc_class, content),
                        "Item description buttons missing correct isDictating class binding.")

if __name__ == '__main__':
    unittest.main()
