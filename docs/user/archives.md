# Archives

Wheels and source distributions use the ZIP and tar format to distribute
multiple files within a single artifact. To avoid archive differential / confusion
attacks due to complexities of archive formats, PyPI rejects archives which
use unnecessary and uncommon features of archives, such as archives that are
designated for multiple disks or archives that are constructed to intentionally
confuse archive implementations.

This page details some of the the archive format features that PyPI rejects so if you
encounter an error you can debug the issue and upload the fixed archive to PyPI.

## Multiple or malformed central directory

Archives often support having multiple central directories
or indexes to allow for "append-only" updates. This is not allowed in archives
on PyPI to avoid confusion while handling multiple central directories.
Additionally, central directories must be specified correctly such that
none of the central directory can be missed or misinterpreted
(such as the offset within the archive, size, etc).

## Missing file in central directory

This error occurs when a file is within the archive but the
file is not recorded in the central directory. This may occur when
a file is "deleted" by removal from the central directory but its
contents are not removed from the archive file itself. This can also
occur if the central directory references a file whose data is not
within the archive.

## Duplicate file entries

There is more than one entry that shares the same name as another entry
within the archive, either within the "central directory" of file entries
or multiple entries. This is disallowed as some implementations process
duplicates differently.

## Filename is not valid

The names of files within the archive must all be UTF-8 encoded bytes
without unprintable characters.
Unprintable characters as the Unicode codepoints `0x00-0x20` and `0x7F`.

## Negative offset

One of the relative offsets specified within the archive
is negative instead of positive. 

## Duplicate extra metadata

There is two or more ZIP extra metadata field 
with the same ID that have security relevance, such
as marking a ZIP as ZIP64 or defining the Unicode filename.

## Trailing data or comments

Many archives support trailing or prepended data
or comments within records. PyPI disallows these features
to avoid smuggling other archive records within comments.
