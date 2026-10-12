# Independent delivery fixture

This fixture is not the support-client benchmark or its immutable acceptance
contract. It documents a real isolated migration and explicit controlled seed.

Migration, before any explicit accounts:

```text
/opt/venv/bin/python main.py migrate_fresh
```

The supervisor then executes the reviewed VERTICAL fixture inputs explicitly.
There are no demo/default accounts at migration. The real negative fixture
documents a failing command and must not become a successful reproduction:

```text
/opt/venv/bin/python main.py reject
```
