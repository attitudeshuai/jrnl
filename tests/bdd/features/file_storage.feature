# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

Feature: Journals iteracting with the file system in a way that users can see

    Scenario: Adding entries to a Folder journal should generate date files
        Given we use the config "empty_folder.yaml"
        When we run "jrnl 23 July 2013: Testing folder journal."
        Then we should get no error
        And the journal directory should contain
            """
            2013/07/23.txt
            """

    Scenario: Adding multiple entries to a Folder journal should generate multiple date files
        Given we use the config "empty_folder.yaml"
        When we run "jrnl 23 July 2013: Testing folder journal."
        And we run "jrnl 3/7/2014: Second entry of journal."
        Then we should get no error
        And the journal directory should contain
            """
            2013/07/23.txt
            """

    Scenario: If the journal and its parent directory don't exist, they should be created
        Given we use the config "missing_directory.yaml"
        Then the journal should not exist
        When we run "jrnl This is a new entry in my journal"
        Then the journal should exist
        When we run "jrnl -99 --short"
        Then the output should contain "This is a new entry in my journal"

    Scenario: If the journal file doesn't exist, then it should be created
        Given we use the config "missing_journal.yaml"
        Then the journal should not exist
        When we run "jrnl This is a new entry in my journal"
        Then the journal should exist
        When we run "jrnl -99 --short"
        Then the output should contain "This is a new entry in my journal"

    @on_posix
    Scenario: If the directory for a Folder journal ending in a slash ('/') doesn't exist, then it should be created
        Given we use the config "missing_directory.yaml"
        Then the journal "endslash" directory should not exist
        When we run "jrnl endslash This is a new entry in my journal"
        Then the journal "endslash" directory should exist
        When we run "jrnl endslash -1"
        Then the output should contain "This is a new entry in my journal"

    @on_win
    Scenario: If the directory for a Folder journal ending in a backslash ('\') doesn't exist, then it should be created
        Given we use the config "missing_directory.yaml"
        Then the journal "endbackslash" directory should not exist
        When we run "jrnl endbackslash This is a new entry in my journal"
        Then the journal "endbackslash" directory should exist
        When we run "jrnl endbackslash -1"
        Then the output should contain "This is a new entry in my journal"

    Scenario: Creating journal with relative path should update to absolute path
        Given we use no config
        When we run "jrnl hello world" and enter
            """
            test.txt
            n
            \n
            """
        Then the output should contain "Journal 'default' created"
        When we change directory to "subfolder"
        And we run "jrnl -n 1"
        Then the output should contain "hello world"

    Scenario: the temporary filename suffix should default to ".jrnl"
        Given we use the config "editor.yaml"
        When we run "jrnl --edit"
        Then the editor should have been called
        Then the editor filename should end with ".jrnl"

    Scenario: the temporary filename suffix should be "-{template_filename}"
        Given we use the config "editor_markdown_extension.yaml"
        When we run "jrnl --edit"
        Then the editor filename should end with "-extension.md"

    @on_posix
    Scenario: Saving through a symlink updates the linked file and keeps the link
        Given we use the config "simple.yaml"
        And the journal file is a symbolic link to a file in another directory
        And the journal file permissions are "640"
        And we note the journal file permissions
        When we run "jrnl 2 February 2024: Entry written through a symlink"
        Then we should get no error
        And the journal path should still be a symbolic link
        And the file the journal points at should contain "Entry written through a symlink"
        And the journal file permissions should be unchanged
        And no temporary files should be left in the journal directory

    @on_posix
    Scenario: Deleting an entry through a symlink updates the linked file
        Given we use the config "simple.yaml"
        And the journal file is a symbolic link to a file in another directory
        When we run "jrnl 8 February 2024: Doomed symlink entry"
        And we run "jrnl -contains Doomed --delete" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        And the journal path should still be a symbolic link
        And the file the journal points at should not contain "Doomed symlink entry"

    @on_posix
    Scenario: Saving a journal with multiple hard links keeps every name current
        Given we use the config "simple.yaml"
        And the journal file has another hard link at "hardlinked.journal"
        When we run "jrnl 3 February 2024: Entry written through a hard link"
        Then we should get no error
        And the journal file and "hardlinked.journal" should still be the same file
        And the file "hardlinked.journal" should contain "Entry written through a hard link"
        And no temporary files should be left in the journal directory

    @on_posix
    Scenario: Saving into a non-writable journal directory fails before writing
        Given we use the config "simple.yaml"
        And we note the journal file content
        And the journal directory is not writable
        When we run "jrnl 4 February 2024: Entry that cannot be saved"
        Then we should get an error
        And the error output should contain "is not writable"
        And the journal file content should be unchanged
        And no temporary files should be left in the journal directory

    @on_posix
    Scenario: Saving through a dangling symlink fails and leaves the link alone
        Given we use the config "simple.yaml"
        And the journal path is a dangling symbolic link
        When we run "jrnl 5 February 2024: Entry into the void"
        Then we should get an error
        And the error output should contain "symbolic link"
        And the journal path should still be dangling
        And no temporary files should be left in the journal directory

    @on_posix
    Scenario: A journal path that is a symlink to a directory can't be saved
        Given we use the config "simple.yaml"
        And the journal path is a symbolic link to a directory
        When we run "jrnl 6 February 2024: Entry toward a directory"
        Then we should get an error
        And the error output should contain "directory, not a file"
        And the journal path should still be a symbolic link

    @on_posix
    Scenario: Saving a read-only journal with hard links is refused to protect the names
        Given we use the config "simple.yaml"
        And the journal file has another hard link at "hardlinked.journal"
        And we note the journal file content
        And the journal file is not writable
        When we run "jrnl 7 February 2024: Entry that cannot be saved"
        Then we should get an error
        And the error output should contain "hard links"
        And the journal file content should be unchanged
        And the journal file and "hardlinked.journal" should still be the same file
