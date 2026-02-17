# ROS2Bag Reader

![PyPI - License](https://img.shields.io/pypi/l/ros2bag-reader)
![PyPI - Version](https://img.shields.io/pypi/v/ros2bag-reader)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ros2bag-reader)
![PyPI Downloads](https://pepy.tech/badge/ros2bag-reader)

A lightweight Python utility for reading **ROS 2 (rosbag2)** recordings stored with the default `sqlite3` backend.

`ROS2BagReader` provides:

- Direct access to deserialized ROS messages.
- Convenient NumPy array extraction from message fields.
- Flexible timestamp handling (raw, bag-relative, topic-relative).
- Automatic support for split bag files.
- Simple bag metadata summary.

The reader operates at the **bag folder level** (the directory containing `metadata.yaml`), not individual `.db3` files.

## Description

ROS 2 recordings created with:

```bash
ros2 bag record ...
````

generate a folder containing:

```
recording/
├── metadata.yaml
├── recording_0.db3
├── recording_1.db3
└── ...
```

`ROS2BagReader`:

* Parses `metadata.yaml`
* Opens all `.db3` files automatically
* Deserializes messages using `rosidl_runtime_py`
* Provides NumPy-ready data extraction utilities

It is designed for **data analysis, plotting, and post-processing workflows**, especially inside Jupyter notebooks.

## Installation

Python **3.10 or greater** is required.

You can intall the module with pip using.

```
pip install ros2bag-reader
```

Or you can copy the module into your project or install it as a local package.

### Dependencies

The library requires:

```python
dependencies = [
    "numpy>=1.24.0",
    "rosidl-runtime-py>=0.9.3",
    "rclpy>=3.3.16",
    "PyYAML>=6.0.3",
    "setuptools>=82.0.0",
    "typeguard>=4.5.0",
    "jinja>=3.1.6",
]
```

## Simple Usage Example

Example using a `turtlesim` recording:

```python
from ros2bag_reader import ROS2BagReader

reader = ROS2BagReader("recording")

reader.summary()

pose = reader.get_messages("/turtle1/pose")

pose_data = reader.get_field_array(
    "/turtle1/pose",
    ["x", "y", "theta"]
)

timestamps = reader.get_time_array(
    "/turtle1/pose",
    reference="topic"
)

reader.close()
```

For a complete example including plotting and data visualization,
see the Jupyter notebook in the `examples/` folder.

## Class Reference

### `ROS2BagReader(bag_folder: str)`

Initialize the reader from a ROS 2 bag folder.

**Parameters**

* `bag_folder` — Path to the directory containing `metadata.yaml`

---

### `close()`

Closes all open SQLite database connections.

Call this when finished reading the bag to release file handles.

---

### `get_messages(topic_name: str)`

Retrieve all messages from a topic.

**Returns**

```python
list[(timestamp_ns: int, message: ROS message instance)]
```

Timestamps are returned in **nanoseconds since epoch**.

---

### `summary()`

Print a human-readable summary of the bag:

* Storage backend
* Duration
* Total message count
* Number of database files
* Per-topic type and message count

---

### `get_time_array(topic_name: str, unit="s", reference="topic")`

Return timestamps as a NumPy array.

### Parameters

* `unit`

  * `"s"` → seconds (float64)
  * `"ns"` → nanoseconds (int64)

* `reference`

  * `"topic"` → relative to first message of the topic
  * `"bag"` → relative to bag start time
  * `"raw"` → no normalization (epoch time)

### Returns

```python
np.ndarray
```

---

### `get_field_array(topic_name: str, fields: list[str], return_timestamps=False)`

Extract selected numeric fields into a NumPy array.

Supports:

* Nested attributes using dot notation
* Indexed access for array fields

### Examples

```python
["x", "y", "theta"]

["pose.position.x", "pose.position.y"]

["ranges[0]", "ranges[10]"]
```

### Returns

If `return_timestamps=False`:

```python
np.ndarray shape (N, len(fields))
```

If `return_timestamps=True`:

```python
timestamps_ns, data_array
```