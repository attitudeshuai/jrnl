# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

Feature: Journal reachability in listings and installation self-check

    Scenario: Listing warns about a missing journal but still succeeds
        Given we use the config "multiple.yaml"
        When we run "jrnl --list"
        Then we should get no error
        And the standard output should not contain "missing"
        And the error output should contain "ideas"
        And the error output should contain "does-not-exist.journal"
        And the error output should contain "Journal path does not exist"
        And the error output should contain "6 journal(s) configured"

    Scenario: Listing a missing journal never creates it
        Given we use the config "missing_journal.yaml"
        When we run "jrnl --list"
        Then we should get no error
        And the error output should contain "missing"
        And journal "default" should not exist

    Scenario: Listing an encrypted journal reports locked without a password prompt
        Given we use the config "basic_encrypted.yaml"
        When we run "jrnl --list --format json"
        Then we should get no error
        And we should not be prompted for a password
        And the output should contain ""status": "locked""
        And the output should contain ""type": "file""
        And the output should not contain "entry_count"
        And the output should contain ""locked": 1"

    Scenario Outline: Listing recognizes each directory journal type
        Given we use the config "<config_file>"
        When we run "jrnl --list --format json"
        Then we should get no error
        And the output should contain ""status": "readable""
        And the output should contain ""type": "<type>""
        And the output should contain "entry_count"

        Examples: journal types
            | config_file        | type   |
            | basic_folder.yaml  | folder |
            | basic_dayone.yaml  | dayone |

    Scenario: Text listing stays unchanged when journals are missing
        Given we use the config "multiple.yaml"
        When we run "jrnl --list"
        Then the output should match
            """
            Journals defined in config \(.+multiple\.yaml\)
             \* .* -> .*
            """
        And the standard output should not contain "readable"
        And the standard output should not contain "locked"

    Scenario: The installation self-check agrees with the listing
        Given we use the config "multiple.yaml"
        When we run "jrnl --doctor"
        Then we should get no error
        And the output should contain "jrnl installation check"
        And the output should contain "multiple.yaml"
        And the output should contain "missing, file"
        And the output should contain "readable, file"
        And the output should contain "Summary: 6 configured"
        And the error output should contain "ideas"
        And journal "ideas" should not exist

    Scenario: The installation self-check reports locked journals
        Given we use the config "basic_encrypted.yaml"
        When we run "jrnl --doctor"
        Then we should get no error
        And we should not be prompted for a password
        And the output should contain "locked, file"
