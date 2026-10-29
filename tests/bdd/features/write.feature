# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

Feature: Writing new entries.

    Scenario Outline: Multiline entry with punctuation should keep title punctuation
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl This is. the title\\n This is the second line"
        And we run "jrnl -n 1"
        Then the output should contain "This is. the title"

        Examples: configs
        | config_file       |
        | simple.yaml       |
        | empty_folder.yaml |
        | dayone.yaml       |
        | encrypted.yaml    |

    Scenario Outline: Single line entry with period should be split at period
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl This is. the title"
        And we run "jrnl -1"
        Then the output should contain "| the title"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: CJK entry should be split at fullwidth period without following space.
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl 七転び。八起き"
        And we run "jrnl -1"
        Then the output should contain "| 八起き"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: Writing an entry from command line should store the entry
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl 23 july 2013: A cold and stormy day. I ate crisps on the sofa."
        Then we should get no error
        When we run "jrnl -n 1"
        Then the output should contain "2013-07-23 09:00 A cold and stormy day."

        Examples: configs
        | config_file       |
        | simple.yaml       |
        | empty_folder.yaml |
        | dayone.yaml       |
        | encrypted.yaml    |

    Scenario Outline: Writing a partial entry from command line with edit flag should go to the editor
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl this is a partial --edit"
        Then we should get no error
        Then the editor should have been called
        And the editor file content should be
            """
            this is a partial
            """

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_dayone.yaml    |
        | basic_folder.yaml    |

    Scenario Outline: Clearing the editor's contents should yield "No text received" message
        Given we use the config "<config_file>"
        And we write nothing to the editor if opened
        And we use the password "test" if prompted
        When we run "jrnl --edit"
        Then the error output should contain "No text received from editor. Were you trying to delete all the entries?"
        And the editor should have been called

        Examples: configs
        | config_file          |
        | editor.yaml          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_dayone.yaml    |
        | basic_folder.yaml    |

    Scenario Outline: Writing an empty entry from the command line should yield "No entry to save" message
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl" and enter "\x04"
        Then the error output should contain "No entry to save, because no text was received"
        When we run "jrnl" and enter " \t \n \x04"
        Then the error output should contain "No entry to save, because no text was received"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: Writing an empty entry from the command line with no editor should yield nothing
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl --config-override editor ''" and enter ""
        Then the stdin prompt should have been called
        And the output should be empty
        And the error output should contain "To finish writing, press"
        And the editor should not have been called

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: Writing an entry does not print the entire journal
        # https://github.com/jrnl-org/jrnl/issues/87
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl 23 july 2013: A cold and stormy day. I ate crisps on the sofa."
        Then we should get no error
        When we run "jrnl -n 1"
        Then the output should not contain "Life is good"

        Examples: configs
        | config_file              |
        | editor.yaml              |
        | editor_empty_folder.yaml |
        | dayone.yaml              |
        | encrypted.yaml           |

    Scenario Outline: Embedded period stays in title
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl 04-24-2014: Created a new website - empty.com. Hope to get a lot of traffic."
        Then we should get no error
        When we run "jrnl -1"
        Then the output should be
            """
            2014-04-24 09:00 Created a new website - empty.com.
            | Hope to get a lot of traffic.
            """

        Examples: configs
        | config_file       |
        | simple.yaml       |
        | empty_folder.yaml |
        | dayone.yaml       |
        | encrypted.yaml    |

    Scenario Outline: Write and read emoji support
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl 23 july 2013: 🌞 sunny day. Saw an 🐘"
        Then we should get no error
        When we run "jrnl -n 1"
        Then the output should contain "🌞"
        And the output should contain "🐘"

        Examples: configs
        | config_file       |
        | simple.yaml       |
        | empty_folder.yaml |
        | dayone.yaml       |
        | encrypted.yaml    |

    Scenario Outline: Writing an entry at the prompt (no editor) should store the entry
        Given we use the config "<config_file>"
        And we use the password "bad doggie no biscuit" if prompted
        When we run "jrnl" and type "25 jul 2013: I saw Elvis. He's alive."
        Then we should get no error
        When we run "jrnl -on '2013-07-25'"
        Then the output should contain "2013-07-25 09:00 I saw Elvis."
        And the output should contain "| He's alive."

        Examples: configs
        | config_file       |
        | simple.yaml       |
        | empty_folder.yaml |
        | encrypted.yaml    |

    @todo
    Scenario: Writing an entry at the prompt (no editor) in DayOne journal
    # Need to test DayOne w/out an editor

    Scenario: Writing into Dayone
        Given we use the config "dayone.yaml"
        When we run "jrnl 01 may 1979: Being born hurts."
        And we run "jrnl -until 1980"
        Then the output should be "1979-05-01 09:00 Being born hurts."

    Scenario: Writing into Dayone adds extended metadata
        Given we use the config "dayone.yaml"
        When we run "jrnl 01 may 1979: Being born hurts."
        And we run "jrnl --export json"
        Then we should get no error
        And the output should be valid JSON
        Given we parse the output as JSON
        Then "entries" in the parsed output should have 5 elements
        And "entries.0.creator" in the parsed output should be
            """
            software_agent
            os_agent
            host_name
            generation_date
            device_agent
            """
        And "entries.0.creator.software_agent" in the parsed output should contain
            """
            jrnl
            """

    Scenario: Title with an embedded period on DayOne journal
        Given we use the config "dayone.yaml"
        When we run "jrnl 04-24-2014: Ran 6.2 miles today in 1:02:03. I am feeling sore because I forgot to stretch."
        Then we should get no error
        When we run "jrnl -1"
        Then the output should be
            """
            2014-04-24 09:00 Ran 6.2 miles today in 1:02:03.
            | I am feeling sore because I forgot to stretch.
            """

    Scenario: Opening an folder that's not a DayOne folder should treat as folder journal
        Given we use the config "empty_folder.yaml"
        When we run "jrnl 23 july 2013: Testing folder journal."
        Then we should get no error
        When we run "jrnl -1"
        Then the output should be "2013-07-23 09:00 Testing folder journal."

    Scenario Outline: Count when adding a single entry via --edit
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we append to the editor if opened
            """
            [2021-11-13] worked on jrnl tests
            """
        When we run "jrnl --edit"
        Then the error output should contain "3 entries found"
        And the error output should contain "1 entry added"


        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        #| basic_dayone.yaml    | @todo


    Scenario Outline: Correctly count when adding multiple entries via --edit
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we append to the editor if opened
            """
            [2021-11-11] worked on jrnl tests
            [2021-11-12] worked on jrnl tests again
            [2021-11-13] worked on jrnl tests a little bit more
            """
        When we run "jrnl --edit"
        Then the error output should contain "3 entries found"
        And the error output should contain "3 entries added"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        #| basic_dayone.yaml    | @todo


    Scenario Outline: Correctly count when removing entries via --edit
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened
            """
            [2021-11-13] I am replacing my whole journal with this entry
            """
        When we run "jrnl --edit"
        Then the output should contain "2 entries deleted"
        And the output should contain "1 entry modified"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        #| basic_dayone.yaml    | @todo


    Scenario Outline: Correctly count modification when running --edit to replace a single entry
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened
            """
            [2021-11-13] I am replacing the last entry with this entry
            """
        When we run "jrnl --edit -1"
        Then the error output should contain "1 entry modified"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        #| basic_dayone.yaml    | @todo


    Scenario Outline: Count modifications when editing whole journal and adding to last entry
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we append to the editor if opened
            """
            This is a small addendum to my latest entry.
            """
        When we run "jrnl --edit"
        Then the error output should contain "3 entries found"
        And the error output should contain "1 entry modified"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: No "Entry added" message should appear when writing to the default journal
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        When we run "jrnl This is a new entry"
        Then the output should not contain "Entry added"
        And we should get no error

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario: An "Entry added" message should appear when writing to a non-default journal
        Given we use the config "multiple.yaml"
        And we use the password "test" if prompted
        When we run "jrnl work This is a new entry"
        Then the output should contain "Entry added to work journal"
        And we should get no error

    Scenario Outline: Tags are saved when an entry is edited with --edit and can be searched afterward
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we append to the editor if opened
            """
            @newtag
            """
        When we run "jrnl --edit -1"
        Then the error output should contain "1 entry modified"
        When we run "jrnl --tags @newtag"
        Then the output should contain
            """
            1 entry found
            """

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: An editor saving a byte order mark produces a clean new entry
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened the raw bytes "77u/bXkgYm9tIHRpdGxlCg=="
        When we run "jrnl"
        Then we should get no error
        When we run "jrnl -1"
        Then the output should contain "my bom title"
        And the output should not contain a byte order mark character
        And the journal should not contain a byte order mark

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: An editor saving Windows line endings produces a clean new entry
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened the raw bytes "bXkgY3JsZiB0aXRsZQ0Kc2Vjb25kIGxpbmUNCg=="
        When we run "jrnl"
        Then we should get no error
        When we run "jrnl -1"
        Then the output should contain "my crlf title"
        And the output should contain "second line"
        And the output should not contain carriage returns
        And the journal should not contain carriage returns

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: A byte order mark before the first date header does not hide it in --edit
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened the raw bytes "77u/WzIwMjEtMTEtMTNdIEkgYW0gcmVwbGFjaW5nIG15IHdob2xlIGpvdXJuYWwgd2l0aCB0aGlzIGVudHJ5Cg=="
        When we run "jrnl --edit"
        Then the output should contain "2 entries deleted"
        And the output should contain "1 entry modified"
        When we run "jrnl -1"
        Then the output should contain "2021-11-13 00:00 I am replacing my whole journal with this entry"
        And the output should not contain a byte order mark character

        Examples: configs
        | config_file        |
        | basic_onefile.yaml |
        | basic_folder.yaml  |

    Scenario Outline: A byte order mark on its own is treated like an empty editor in append mode
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we write to the editor if opened the raw bytes "77u/"
        When we run "jrnl"
        Then we should get an error
        And the error output should contain "No entry to save, because no text was received"

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: A byte order mark with only whitespace is treated like an empty editor in --edit
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we take a snapshot of the journal
        And we write to the editor if opened the raw bytes "77u/IA0K"
        When we run "jrnl --edit"
        Then the error output should contain "No text received from editor. Were you trying to delete all the entries?"
        And the journal should match the snapshot

        Examples: configs
        | config_file          |
        | basic_onefile.yaml   |
        | basic_encrypted.yaml |
        | basic_folder.yaml    |
        | basic_dayone.yaml    |

    Scenario Outline: Undecodable editor output is preserved and the journal is left untouched
        Given we use the config "<config_file>"
        And we use the password "test" if prompted
        And we take a snapshot of the journal
        And we write to the editor if opened the raw bytes "//6AbXkgdW5kZWNvZGFibGUgdGV4dCCAgQo="
        When we run "jrnl"
        Then we should get an error
        And the error output should contain "could not be read"
        And the preserved editor content at the reported path should exist
        And the journal should match the snapshot

        Examples: configs
        | config_file        |
        | basic_onefile.yaml |
        | basic_folder.yaml  |
        | basic_dayone.yaml  |

    Scenario: Undecodable editor output for an encrypted journal is preserved as ciphertext
        Given we use the config "basic_encrypted.yaml"
        And we use the password "test" if prompted
        And we take a snapshot of the journal
        And we write to the editor if opened the raw bytes "//6AbXkgdW5kZWNvZGFibGUgdGV4dCCAgQo="
        When we run "jrnl"
        Then we should get an error
        And the error output should contain "could not be read"
        And the error output should contain "not stored as plain text"
        And the preserved editor content at the reported path should exist
        And the preserved editor content should not contain plain text
        And the journal should match the snapshot

    Scenario: A single-file CRLF journal is normalized on first save and stable on the second
        Given we use the config "basic_onefile.yaml"
        And the journal uses Windows line endings
        When we run "jrnl --export text"
        Then we should get no error
        And the output should not contain carriage returns
        When we run "jrnl 2020-08-29 12:00: Brand new normalization entry"
        Then we should get no error
        And the journal should not contain carriage returns
        And we take a snapshot of the journal
        When we run "jrnl --edit"
        Then we should get no error
        And the journal should match the snapshot

    Scenario: Saving a folder journal with Windows line endings only rewrites the affected date
        Given we use the config "basic_folder.yaml"
        And the journal uses Windows line endings
        When we run "jrnl 2020-08-29 12:00: Brand new normalization entry"
        Then we should get no error
        And the journal file "2020/08/29.txt" should not contain carriage returns
        And the journal file "2020/08/31.txt" should contain carriage returns
        When we run "jrnl --export text"
        Then the output should not contain carriage returns
        And we take a snapshot of the journal
        When we run "jrnl --edit"
        Then we should get no error
        And the journal should match the snapshot
        And the journal file "2020/08/31.txt" should contain carriage returns
