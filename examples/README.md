# Notes for message packets

## ns_messages.json

These are the shared message packets used among the various NorthStar UAS
modules.  I try to carry a bit of history as messages or message strutures
change to allow some backwards compatibility.  But I do delete some of the
oldest messages to avoid carrying too much cruft forward that will never be used
again.

* IMU message packing
  * 3754.82165 = +/-500dps (8.7266rps) spread across int16
  * 835.296217 = +/-4g (39.228mps^2) spread across int16
  * 3000 = mags might range +/- 10?
