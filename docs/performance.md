Opens now call stat twice:
- once before the open to make sure we aren't going to truncate an inode that we need.
- once after the open, so we know what file is getting read.
Both of these can be reduced.
The first only needs to be done when the flags are TRUNC.
The second doesn't need to happen if we have open-numbering. The stat can be recovered from the close(), or vice versa.
The second only needs to happen if the first does not.
Perhaps the stats on dup can even be removed.
