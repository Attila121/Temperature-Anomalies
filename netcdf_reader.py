# Read classic CDF-1/CDF-2 NetCDF snapshots without extra dependencies.

import math
import struct

import numpy as np

NC_TYPES = {1: ">i1", 2: "S1", 3: ">i2", 4: ">i4", 5: ">f4", 6: ">f8"}


class ClassicHeader:
    """Small read-only CDF-1/CDF-2 header reader for input inspection only."""

    def __init__(self, payload):
        self.payload = payload
        self.offset = 4
        self.version = payload[3]
        if payload[:3] != b"CDF" or self.version not in (1, 2):
            raise ValueError("expected classic CDF-1 or CDF-2 NetCDF")
        self.records = self.uint()
        self.dimensions = self.list(10, lambda: {"name": self.name(), "size": self.uint()})
        self.attributes = self.attrs()
        self.variables = self.list(11, self.variable)

    def uint(self):
        value = struct.unpack_from(">I", self.payload, self.offset)[0]
        self.offset += 4
        return value

    def name(self):
        size = self.uint()
        raw = self.payload[self.offset:self.offset + size]
        self.offset += (size + 3) // 4 * 4
        return raw.decode("utf-8", errors="replace")

    def list(self, expected_tag, item):
        tag, count = self.uint(), self.uint()
        if tag == count == 0:
            return []
        if tag != expected_tag:
            raise ValueError(f"unexpected NetCDF list tag {tag}")
        return [item() for _ in range(count)]

    def attribute(self):
        name, kind, count = self.name(), self.uint(), self.uint()
        dtype = np.dtype(NC_TYPES[kind])
        size = dtype.itemsize * count
        raw = self.payload[self.offset:self.offset + size]
        self.offset += (size + 3) // 4 * 4
        value = raw.decode("utf-8", errors="replace") if kind == 2 else np.frombuffer(raw, dtype=dtype).tolist()
        return name, value

    def attrs(self):
        return dict(self.list(12, self.attribute))

    def variable(self):
        name = self.name()
        dims = [self.uint() for _ in range(self.uint())]
        attributes = self.attrs()
        kind, size = self.uint(), self.uint()
        begin = self.uint()
        if self.version == 2:
            begin = (begin << 32) | self.uint()
        return {"name": name, "dimension_ids": dims, "attributes": attributes,
                "type": kind, "record_bytes": size, "begin": begin}

    def read_array(self, name):
        """Read a fixed-size or record variable without applying packed scaling."""
        var = next(v for v in self.variables if v["name"] == name)
        dims = [self.dimensions[i]["size"] for i in var["dimension_ids"]]
        dtype = np.dtype(NC_TYPES[var["type"]])
        if dims and dims[0] == 0:
            record_vars = [v for v in self.variables if v["dimension_ids"] and self.dimensions[v["dimension_ids"][0]]["size"] == 0]
            stride = sum(v["record_bytes"] for v in record_vars)
            shape = (self.records, *dims[1:])
            tail_strides = tuple(dtype.itemsize * math.prod(dims[i + 1:]) for i in range(1, len(dims)))
            values = np.ndarray(shape, dtype=dtype, buffer=self.payload,
                                offset=var["begin"], strides=(stride, *tail_strides)).copy()
        else:
            values = np.frombuffer(self.payload, dtype=dtype, count=math.prod(dims),
                                   offset=var["begin"]).reshape(dims).copy()
        return values, var["attributes"]

    def read_vector(self, name):
        values, attrs = self.read_array(name)
        if values.ndim != 1:
            raise ValueError("expected a one-dimensional coordinate")
        return values, attrs


