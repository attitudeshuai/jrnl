# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

Feature: Restore deleted entries
    Scenario Outline: --restore-deleted puts the most recently deleted entries back
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl --delete -from 2020-09-01" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-29 11:11 Entry the first.
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            """
        When we run "jrnl --restore-deleted"
        Then we should get no error
        And the output should be empty
        And the error output should contain "1 entry restored"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-29 11:11 Entry the first.
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            2020-09-24 09:14 The third entry finally after weeks without writing.
            """

        Examples: Configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |


    Scenario Outline: Restoring twice restores the batch only once
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl --delete -from 2020-09-01" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        When we run "jrnl --restore-deleted"
        Then the error output should contain "1 entry restored"
        When we run "jrnl --restore-deleted"
        Then we should get no error
        And the error output should contain "No deleted entries to restore"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-29 11:11 Entry the first.
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            2020-09-24 09:14 The third entry finally after weeks without writing.
            """

        Examples: Configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |


    Scenario Outline: A new deletion replaces the previous recoverable batch
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl --delete -from 2020-09-01" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        When we run "jrnl --delete -to 2020-08-29" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        When we run "jrnl --restore-deleted"
        Then the error output should contain "1 entry restored"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-29 11:11 Entry the first.
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            """
        When we run "jrnl --restore-deleted"
        Then the error output should contain "No deleted entries to restore"

        Examples: Configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_folder.yaml    |


    Scenario: Restoring into a folder journal rebuilds the emptied day file
        Given we use the config "basic_folder.yaml"
        When we run "jrnl --delete -from 2020-09-01" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        And the journal directory should contain
            """
            2020/08/29.txt
            2020/08/31.txt
            """
        When we run "jrnl --restore-deleted"
        Then the error output should contain "1 entry restored"
        And the journal directory should contain
            """
            2020/09/24.txt
            """


    Scenario Outline: Entries removed in the editor are restored through the same record
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened
            """
            [2021-11-13 09:00] I am replacing my whole journal with this entry
            """
        When we run "jrnl --edit"
        Then the output should contain "2 entries deleted"
        When we run "jrnl --restore-deleted"
        Then the error output should contain "2 entries restored"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            2020-09-24 09:14 The third entry finally after weeks without writing.
            2021-11-13 09:00 I am replacing my whole journal with this entry
            """
        When we run "jrnl --restore-deleted"
        Then the error output should contain "No deleted entries to restore"

        Examples: Configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |


    Scenario: Restoring with nothing deleted is reported as nothing to restore
        Given we use the config "basic_onefile.yaml"
        When we run "jrnl --restore-deleted"
        Then we should get no error
        And the error output should contain "No deleted entries to restore"
        When we run "jrnl -99 --short"
        Then the output should contain "Entry the first"


    Scenario: A corrupt recovery record restores nothing and leaves the journal unchanged
        Given we use the config "basic_onefile.yaml"
        When we run "jrnl --delete -from 2020-09-01" and enter
            """
            Y
            """
        Then the error output should contain "1 entry deleted"
        Given we corrupt the deleted entries record
        When we run "jrnl --restore-deleted"
        Then we should get an error
        And the error output should contain "couldn't be read"
        When we run "jrnl -99 --short"
        Then the output should be
            """
            2020-08-29 11:11 Entry the first.
            2020-08-31 14:32 A second entry in what I hope to be a long series.
            """
        When we run "jrnl --restore-deleted"
        Then we should get an error
