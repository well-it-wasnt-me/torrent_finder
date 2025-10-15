torrent_finder documentation
============================

``torrent_finder`` automates the hunt for the "best" torrent by pulling results from a Torznab/Jackett
endpoint, ranking the candidates, and handing the winner directly to Transmission. The project favors
simple configuration, readable logging, and a workflow that you can script or invoke ad-hoc.

Key capabilities
----------------
- Query Torznab/Jackett feeds and score candidates by seeders and leechers.
- Apply configuration defaults from ``config.json`` but allow one-off CLI overrides.
- Dispatch the chosen magnet to Transmission via RPC or ``transmission-remote``.

Command-line pit stop
---------------------

.. code-block:: bash

   python main.py "Everything Everywhere All at Once" \
     --config config.json \
     --start \
     --categories "2000,5000"

What you'll find in this documentation
--------------------------------------
- A quick path to installation and verification.
- Guidance on shaping ``config.json`` for Torznab, Transmission, and logging.
- Usage patterns for the CLI and an API reference for extending the toolkit.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting_started
   usage
   configuration

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   modules
