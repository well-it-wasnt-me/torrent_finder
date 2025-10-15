Usage
=====

The CLI glues together configuration loading, Torznab searching, and Transmission handoff. You only
need to supply a title, but most configuration fields can be overridden per invocation.

Basic search
------------

.. code-block:: bash

   python main.py "Drunken Master"

The command above loads ``config.json`` from the project root, queries the configured Torznab feed,
logs the ranked candidates, and sends the top magnet to Transmission using the defaults defined in
the configuration file.

Command-line options
--------------------

title
   Required positional argument that specifies the search phrase sent to Torznab.

--config PATH
   Alternate path to the JSON configuration file. Defaults to ``config.json`` next to ``main.py``.

--download-dir DIR
   Temporary download directory that overrides the Transmission ``download_dir`` setting.

--start / --no-start
   Force the torrent to start immediately or be added in a paused state. If omitted the value from
   configuration is used.

--use-rpc / --use-remote
   Switch between Transmission's RPC interface and the ``transmission-remote`` CLI regardless of
   what the configuration specifies.

--host, --port
   Override the Transmission host and port when connecting over RPC or ``transmission-remote``.

--username, --password
   Credentials for Transmission RPC mode.

--auth
   ``user:pass`` combination for the ``transmission-remote`` CLI.

--categories
   Replace the Torznab category filter for this run (comma-separated list).

--debug
   Elevate logging to ``DEBUG`` regardless of the configuration.

Workflow tips
-------------
- Use the overrides to script batch downloads without touching ``config.json``.
- Pair ``--debug`` with a temporary ``--download-dir`` when diagnosing indexer or Transmission issues.
- If ``transmission-remote`` is not found, toggle RPC mode with ``--use-rpc`` (requires
  ``transmission-rpc`` to be installed in the active environment).
