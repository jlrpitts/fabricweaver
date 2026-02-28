fabricweaver/
│
├── fabricweaver.py          # Main desktop entry point
│
├── core/
│   ├── models.py            # Data models (Device, Interface, VLAN, Link)
│   ├── topology_builder.py  # Builds L2/L3 adjacency graph
│   └── exporter.py          # PNG / PDF export logic
│
├── parser/
│   ├── orchestrator.py      # Parsing entry point
│   ├── vendor_detect.py     # Vendor detection logic
│   └── vendors/
│       ├── cisco_ios.py
│       ├── cisco_nxos.py
│       ├── dell_os10.py
│       └── arista_eos.py
│
├── ssh/
│   ├── ssh_client.py        # SSH connection logic
│   ├── command_sets.py      # Show commands per vendor
│   └── live_collect.py      # Dynamic build mode
│
├── ui/
│   ├── layout.py            # Tkinter layout
│   └── theme.py             # Dark mode styling
│
├── samples/
│
├── requirements.txt
└── start.bat
