"""
Minimal ROS2 node:
- Subscribes: doa/wav_path (std_msgs/String)
- Publishes: doa/angle_deg (std_msgs/Float32), doa/confidence (std_msgs/Float32)

Why: no assumptions about custom audio message types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import rclpy
import soundfile as sf
from rclpy.node import Node
from std_msgs.msg import Float32, String

from doa.dsp import bandpass_sos, apply_offset
from doa.pipeline import eval_center, multi_window_doa
from doa.calibration import load_calibration
@dataclass
class NodeConfig:
    win_s: float = 0.10
    srp_subband: int = 16
    sym_pair: bool = False
    source_distance_m: Optional[float] = None
    bandpass: Optional[Tuple[float, float]] = None
    theta_offset_deg: float = 0.0
    calib_file: Optional[str] = None

    use_multi: bool = True
    multi_t0: float = 0.0
    multi_t1: float = 10.0
    hop_s: float = 0.5
    ambig_eps: float = 0.05
    agg: str = "mode"
class DoaFromWavNode(Node):
    def __init__(self) -> None:
        super().__init__("doa_from_wav")

        self.declare_parameter("win_s", 0.10)
        self.declare_parameter("srp_subband", 16)
        self.declare_parameter("sym_pair", False)
        self.declare_parameter("source_distance_m", rclpy.parameter.Parameter.Type.DOUBLE)
        self.declare_parameter("bandpass_lo_hz", rclpy.parameter.Parameter.Type.DOUBLE)
        self.declare_parameter("bandpass_hi_hz", rclpy.parameter.Parameter.Type.DOUBLE)
        self.declare_parameter("theta_offset_deg", 0.0)
        self.declare_parameter("calib_file", "")

        self.declare_parameter("use_multi", True)
        self.declare_parameter("multi_t0", 0.0)
        self.declare_parameter("multi_t1", 10.0)
        self.declare_parameter("hop_s", 0.5)
        self.declare_parameter("ambig_eps", 0.05)
        self.declare_parameter("agg", "mode")

        self.cfg = self._load_cfg()
        
        self.sub = self.create_subscription(String, "doa/wav_path", self._on_wav, 10)
        self.pub_angle = self.create_publisher(Float32, "doa/angle_deg", 10)
        self.pub_conf = self.create_publisher(Float32, "doa/confidence", 10)

        self.get_logger().info("Ready. Publish WAV path to topic doa/wav_path")

    def _load_cfg(self) -> NodeConfig:
        cfg = NodeConfig()
        cfg.win_s = float(self.get_parameter("win_s").value)
        cfg.srp_subband = int(self.get_parameter("srp_subband").value)
        cfg.sym_pair = bool(self.get_parameter("sym_pair").value)

        sd = self.get_parameter("source_distance_m").value
        cfg.source_distance_m = float(sd) if sd is not None else None

        lo = self.get_parameter("bandpass_lo_hz").value
        hi = self.get_parameter("bandpass_hi_hz").value
        if lo is not None and hi is not None:
            cfg.bandpass = (float(lo), float(hi))

        cfg.theta_offset_deg = float(self.get_parameter("theta_offset_deg").value)
        calib_file = str(self.get_parameter("calib_file").value).strip()
        cfg.calib_file = calib_file if calib_file else None
        if cfg.calib_file:
           cfg.theta_offset_deg = load_calibration(cfg.calib_file)

        cfg.use_multi = bool(self.get_parameter("use_multi").value)
        cfg.multi_t0 = float(self.get_parameter("multi_t0").value)
        cfg.multi_t1 = float(self.get_parameter("multi_t1").value)
        cfg.hop_s = float(self.get_parameter("hop_s").value)
        cfg.ambig_eps = float(self.get_parameter("ambig_eps").value)
        cfg.agg = str(self.get_parameter("agg").value)
        return cfg

    def _on_wav(self, msg: String) -> None:
        path = msg.data.strip()
        if not path:
            return

        try:
            x, fs = sf.read(path, always_2d=True)
            if self.cfg.bandpass is not None:
                x = bandpass_sos(x, fs, float(self.cfg.bandpass[0]), float(self.cfg.bandpass[1]))

            if self.cfg.use_multi:
                theta, _used, _total, dom = multi_window_doa(
                    x=x,
                    fs=fs,
                    t0=self.cfg.multi_t0,
                    t1=self.cfg.multi_t1, 
                    win_s=self.cfg.win_s,
                    hop_s=self.cfg.hop_s,
                    srp_subband=self.cfg.srp_subband,
                    sym_pair=self.cfg.sym_pair,
                    theta_offset_deg=self.cfg.theta_offset_deg,
                    ambig_eps=self.cfg.ambig_eps,
                    agg=self.cfg.agg,
                    source_distance_m=self.cfg.source_distance_m,
                    debug=False,
                )
                conf = float(dom) if self.cfg.agg == "mode" else 1.0
            else:
                ct = 0.5 * (self.cfg.multi_t0 + self.cfg.multi_t1)
                r = eval_center(
                    x=x,
                    fs=fs,
                    center_time_s=ct,
                    win_s=self.cfg.win_s,
                    srp_subband=self.cfg.srp_subband,
                    sym_pair=self.cfg.sym_pair,
                    source_distance_m=self.cfg.source_distance_m,
                )
                theta = apply_offset(r.theta_raw, self.cfg.theta_offset_deg)
                conf = float(r.confidence)

            self.pub_angle.publish(Float32(data=float(theta)))
            self.pub_conf.publish(Float32(data=float(conf)))
            self.get_logger().info(f"{path} -> angle={theta:.2f} deg, conf={conf:.3f}")

        except Exception as e:
            self.get_logger().error(f"Failed for '{path}': {e}")


def main() -> None:
    rclpy.init()
    node = DoaFromWavNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
if __name__ == "__main__":
    main()        