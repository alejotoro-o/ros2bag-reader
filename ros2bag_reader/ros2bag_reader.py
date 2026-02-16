import os
import re
import sqlite3
import yaml
from rosidl_runtime_py.utilities import get_message
from rclpy.serialization import deserialize_message
import numpy as np


class ROS2BagReader:
    """
    Lightweight reader for ROS 2 (rosbag2) recordings stored using the SQLite3
    storage backend.

    This class provides convenient access to:

    - Bag metadata (from `metadata.yaml`)
    - Deserialized ROS messages by topic
    - Time arrays with configurable reference frames
    - Structured NumPy array extraction from message fields

    The reader operates at the bag-folder level (not individual `.db3` files),
    supporting split bag recordings transparently.

    Parameters
    ----------
    bag_folder : str
        Path to the ROS 2 bag directory containing `metadata.yaml`
        and one or more `.db3` database files.

    Raises
    ------
    FileNotFoundError
        If `metadata.yaml` is not found in the provided folder.
    """

    def __init__(self, bag_folder: str):
        """
        Initialize the ROS2BagReader.

        Parses bag metadata, opens all SQLite database files referenced
        in `metadata.yaml`, and builds internal mappings between topic names,
        topic IDs, and ROS message types.

        Parameters
        ----------
        bag_folder : str
            Path to the ROS 2 bag directory.

        Raises
        ------
        FileNotFoundError
            If `metadata.yaml` does not exist in the provided folder.
        """


        self.bag_folder = bag_folder
        self.metadata_path = os.path.join(bag_folder, "metadata.yaml")

        if not os.path.exists(self.metadata_path):
            raise FileNotFoundError("metadata.yaml not found in bag folder")

        # Parse metadata
        with open(self.metadata_path, "r") as f:
            self.metadata = yaml.safe_load(f)["rosbag2_bagfile_information"]

        # Open all db3 files
        self.connections = []
        self.cursors = []

        for file_info in self.metadata["files"]:
            db_path = os.path.join(bag_folder, file_info["path"])
            conn = sqlite3.connect(db_path)
            self.connections.append(conn)
            self.cursors.append(conn.cursor())

        # Build topic map from first DB (schema is identical across splits)
        topics_data = self.cursors[0].execute(
            "SELECT id, name, type FROM topics"
        ).fetchall()

        self.topic_type = {name: type_ for _, name, type_ in topics_data}
        self.topic_id = {name: id_ for id_, name, _ in topics_data}
        self.topic_msg_type = {
            name: get_message(type_)
            for _, name, type_ in topics_data
        }

    def close(self):
        """
        Close all open SQLite connections associated with the bag.

        This should be called when the reader is no longer needed
        to release file handles and database resources.
        """

        for conn in self.connections:
            conn.close()

    def get_messages(self, topic_name: str):
        """
        Retrieve all messages for a given topic.

        Messages are deserialized into their corresponding ROS message types.

        Parameters
        ----------
        topic_name : str
            Name of the topic to retrieve (e.g., "/turtle1/pose").

        Returns
        -------
        list[tuple[int, object]]
            A list of (timestamp, message) tuples where:
            - timestamp is in nanoseconds since epoch (int)
            - message is a deserialized ROS message instance

        Raises
        ------
        ValueError
            If the specified topic does not exist in the bag.
        """


        if topic_name not in self.topic_id:
            raise ValueError(f"Topic {topic_name} not found")

        topic_id = self.topic_id[topic_name]
        msg_type = self.topic_msg_type[topic_name]

        results = []

        for cursor in self.cursors:
            rows = cursor.execute(
                "SELECT timestamp, data FROM messages WHERE topic_id = ?",
                (topic_id,)
            ).fetchall()

            for timestamp, data in rows:
                msg = deserialize_message(data, msg_type)
                results.append((timestamp, msg))

        return results

    def summary(self):
        """
        Print a human-readable summary of the bag contents.

        Displays:

        - Storage backend
        - Total duration (seconds)
        - Total message count
        - Number of database files
        - Per-topic message counts and types

        Information is extracted from `metadata.yaml`.
        """

        info = self.metadata

        print("Bag Summary")
        print("-----------")
        print(f"Storage: {info['storage_identifier']}")
        print(f"Duration: {info['duration']['nanoseconds'] * 1e-9:.2f} seconds")
        print(f"Message Count: {info['message_count']}")
        print(f"Files: {len(info['files'])}")
        print()

        print("Topics:")
        for topic in info["topics_with_message_count"]:
            name = topic["topic_metadata"]["name"]
            type_ = topic["topic_metadata"]["type"]
            count = topic["message_count"]

            print(f"    {name}")
            print(f"        Type: {type_}")
            print(f"        Messages: {count}")
            print()

    def get_time_array(self, topic_name: str, unit:str = "s", reference: str = "topic"):
        """
        Return a NumPy array of timestamps for a given topic.

        Timestamps can be returned in nanoseconds or seconds, and
        can be referenced relative to the bag start, topic start,
        or left as raw epoch time.

        Parameters
        ----------
        topic_name : str
            Name of the topic.
        unit : str, optional
            Time unit of the output:
            - "s"  : seconds (float64)
            - "ns" : nanoseconds (int64)
        reference : str, optional
            Time reference frame:
            - "topic" : relative to the first message of the topic
            - "bag"   : relative to bag start time
            - "raw"   : no normalization (epoch nanoseconds)

        Returns
        -------
        np.ndarray
            Array of timestamps in the specified unit.

        Raises
        ------
        ValueError
            If `reference` or `unit` is invalid.
        """


        timestamps = np.array(
            [t for t, _ in self.get_messages(topic_name)],
            dtype=np.int64
        )

        if reference == "bag":
            bag_start = self.metadata["starting_time"]["nanoseconds_since_epoch"]
            timestamps = timestamps - bag_start

        elif reference == "topic" and len(timestamps) > 0:
            timestamps = timestamps - timestamps[0]

        elif reference == "raw":
            pass

        else:
            raise ValueError("Invalid reference")

        if unit == "s":
            return timestamps / 1e9
        elif unit == "ns":
            return timestamps
        else:
            raise ValueError("Invalid unit")

    def _resolve_attr(self, obj, attr_path: str):
        """
        Resolve a nested attribute path from a ROS message object.

        Supports:

        - Dot notation for nested fields (e.g., "pose.position.x")
        - Indexed access for array fields (e.g., "ranges[0]")

        Parameters
        ----------
        obj : object
            ROS message instance.
        attr_path : str
            Attribute path using dot notation and optional indexing.

        Returns
        -------
        object
            The resolved attribute value.
        """

        parts = attr_path.split(".")
        for part in parts:
            match = re.match(r"(\w+)(\[(\d+)\])?", part)
            attr_name = match.group(1)
            index = match.group(3)

            obj = getattr(obj, attr_name)

            if index is not None:
                obj = obj[int(index)]

        return obj

    def get_field_array(self, topic_name: str, fields: list[str], return_timestamps: bool = False):
        """
        Extract selected numeric fields from a topic into a NumPy array.

        Supports nested fields and indexed access using dot notation,
        for example:

        - "x"
        - "orientation.x"
        - "pose.position.x"
        - "ranges[0]"

        Parameters
        ----------
        topic_name : str
            Name of the topic.
        fields : list[str]
            List of attribute paths to extract.
        return_timestamps : bool, optional
            If True, also return the corresponding timestamps
            (nanoseconds since epoch).

        Returns
        -------
        np.ndarray
            Array of shape (N, len(fields)) containing extracted values.

        or

        tuple[np.ndarray, np.ndarray]
            If `return_timestamps=True`, returns:
            - timestamps (int64, nanoseconds)
            - data array (float64)

        Raises
        ------
        ValueError
            If the topic does not exist.
        """

        msgs = self.get_messages(topic_name)

        data = []
        timestamps = []

        for t, msg in msgs:
            row = []
            for field in fields:
                value = self._resolve_attr(msg, field)
                row.append(value)

            data.append(row)
            timestamps.append(t)

        data = np.asarray(data, dtype=np.float64)

        if return_timestamps:
            return np.asarray(timestamps, dtype=np.int64), data

        return data
