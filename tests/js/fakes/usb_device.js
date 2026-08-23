/**
 * A scripted PTP camera at the WebUSB level.
 *
 * Implements only the surface ClientPTPUSBDevice touches. It parses the
 * containers written to it and replies with real ones, so the transport is
 * exercised against bytes rather than against a mock of itself.
 *
 * The knobs exist because the failures worth testing are the ones a camera
 * inflicts and a happy-path fake never would: a stalled endpoint, a transfer
 * that never returns, a camera that skips the data phase.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  _OC_CLOSE_SESSION,
  _OC_GET_DEVICE_INFO,
  _OC_GET_DEVICE_PROP_VALUE,
  _OC_OPEN_SESSION,
  _OC_SET_DEVICE_PROP_VALUE,
  _PTP_COMMAND,
  _PTP_DATA,
  _PTP_RESPONSE,
  _RC_OK,
  _encodePtpString,
} from "../../../src/interfaces/static/js/camera/vendor/ptp_usb_device.js";

/**
 * A real DeviceInfo payload for an X-S10, taken from the shared byte vectors
 * rather than written by hand, so the fake replays a shape the Python side
 * generated and both suites already assert against.
 */
export const X_S10_DEVICE_INFO_HEX = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../fixtures/camera/ptp_vectors.json", import.meta.url)),
    "utf8"
  )
).device_info.find((v) => v.name === "x_s10").hex;

function defaultConfiguration() {
  return {
    configurationValue: 1,
    interfaces: [
      {
        interfaceNumber: 0,
        alternates: [
          {
            alternateSetting: 0,
            endpoints: [
              // An interrupt endpoint sits alongside the bulk pair on real
              // cameras; discovery has to ignore it.
              { endpointNumber: 3, direction: "in", type: "interrupt" },
              { endpointNumber: 1, direction: "out", type: "bulk" },
              { endpointNumber: 2, direction: "in", type: "bulk" },
            ],
          },
        ],
      },
    ],
  };
}

function container(type, code, txId, payload = new Uint8Array(0)) {
  const packet = new Uint8Array(12 + payload.length);
  const view = new DataView(packet.buffer);
  view.setUint32(0, packet.length, true);
  view.setUint16(4, type, true);
  view.setUint16(6, code, true);
  view.setUint32(8, txId, true);
  packet.set(payload, 12);
  return packet;
}

function int32Payload(value) {
  const bytes = new Uint8Array(4);
  new DataView(bytes.buffer).setInt32(0, value, true);
  return bytes;
}

function fromHex(hex) {
  const clean = hex.replace(/\s+/g, "");
  const bytes = new Uint8Array(clean.length / 2);
  for (let i = 0; i < bytes.length; i += 1) {
    bytes[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}

export class FakeUSBDevice {
  /**
   * @param {object} [options]
   * @param {number[]} [options.stallOn] Operation codes whose next transfer stalls.
   * @param {number[]} [options.hangOn] Operation codes whose read never resolves.
   * @param {number[]} [options.noDataPhaseOn] Codes answered with a response and no data.
   * @param {number} [options.noDataPhaseTimes] How many such replies before the code
   *   behaves normally. Infinite by default; set it to model a camera that drops a
   *   value once and answers on the retry, which is what real hardware does.
   * @param {Record<number, number>} [options.intValues] Property code to int value.
   * @param {Record<number, string>} [options.stringValues] Property code to string value.
   * @param {Record<number, number>} [options.setRejectionCodes] Property code to rc.
   * @param {number} [options.openSessionRc]
   * @param {string} [options.deviceInfoHex]
   * @param {object} [options.configuration] A configuration descriptor to expose.
   * @param {Error} [options.failOpenWith] Thrown from open(), like a busy interface.
   * @param {number} [options.failTransferInTimes] Fail this many reads, then behave.
   * @param {number} [options.wedgeAfterReads] After this many reads, stop completing
   *   them entirely while still accepting writes. Models the observed X-S10 stall,
   *   where a timed-out transfer leaves the IN endpoint blocked for good.
   */
  constructor({
    stallOn = [],
    hangOn = [],
    noDataPhaseOn = [],
    noDataPhaseRc = _RC_OK,
    noDataPhaseTimes = Infinity,
    intValues = {},
    stringValues = {},
    setRejectionCodes = {},
    openSessionRc = _RC_OK,
    deviceInfoHex = X_S10_DEVICE_INFO_HEX,
    configuration = undefined,
    failOpenWith = null,
    failTransferInTimes = 0,
    wedgeAfterReads = Infinity,
  } = {}) {
    this.vendorId = 0x04cb;
    this.productId = 0x02e5;
    this.manufacturerName = "FUJIFILM";
    this.productName = "X-S10";
    this.configuration = null;

    this._declaredConfiguration = configuration ?? defaultConfiguration();
    this._stallOn = new Set(stallOn);
    this._hangOn = new Set(hangOn);
    this._noDataPhaseOn = new Set(noDataPhaseOn);
    this._noDataPhaseRc = noDataPhaseRc;
    this._noDataPhaseLeft = noDataPhaseTimes;
    this._intValues = { ...intValues };
    this._stringValues = { ...stringValues };
    this._setRejectionCodes = { ...setRejectionCodes };
    this._openSessionRc = openSessionRc;
    this._deviceInfo = fromHex(deviceInfoHex);
    this._failOpenWith = failOpenWith;
    // Transport failures the retry loops are expected to ride out. Distinct
    // from hangOn: this fails fast, so a retry can genuinely succeed.
    this._failTransferInTimes = failTransferInTimes;
    this._readsUntilWedge = wedgeAfterReads;
    this._wedged = false;
    this._busyFor = 0;

    this._queue = [];
    this._pendingSet = null;

    /** Every container written, parsed, in order. Tests assert against this. */
    this.sent = [];
    /** Lifecycle calls, so tests can check the device is released and closed. */
    this.calls = [];
  }

  // --- lifecycle ---------------------------------------------------------

  async open() {
    this.calls.push("open");
    if (this._failOpenWith) throw this._failOpenWith;
    this.opened = true;
  }

  async close() {
    this.calls.push("close");
    this.opened = false;
    // Closing rejects every pending transfer, which is the one thing that is
    // certain to free a wedged endpoint.
    this._wedged = false;
    this._readsUntilWedge = this.wedgeAgainAfter ?? Infinity;
    this._queue.length = 0;
    this._pendingSet = null;
  }

  async selectConfiguration(value) {
    this.calls.push(`selectConfiguration(${value})`);
    this.configuration = this._declaredConfiguration;
  }

  async claimInterface(number) {
    this.calls.push(`claimInterface(${number})`);
    this.claimed = number;
  }

  async releaseInterface(number) {
    this.calls.push(`releaseInterface(${number})`);
    this.claimed = null;
  }

  async clearHalt(direction, endpointNumber) {
    this.calls.push(`clearHalt(${direction},${endpointNumber})`);
  }

  /**
   * Endpoint 0. The point of modelling it is that it keeps working when the
   * bulk IN endpoint is wedged, which is the only reason cancelling is possible
   * at all.
   */
  async controlTransferOut(setup, data) {
    this.calls.push(`controlTransferOut(0x${setup.request.toString(16)})`);
    if (setup.request === 0x66) {
      // Device Reset clears the camera's PTP state, which is the thing a USB
      // reopen leaves untouched: the session, and any transaction wedged in it.
      this._sessionOpen = false;
      this._wedged = false;
      this._readsUntilWedge = this.wedgeAgainAfter ?? Infinity;
      this._queue.length = 0;
      this._pendingSet = null;
      this._stuckOnWrite = false;
      this._busyFor = this.resetLeavesBusyFor ?? 0;
    }
    if (setup.request === 0x64) {
      // Cancel: the camera abandons the transaction and the endpoint frees.
      // Whether real hardware honours this is the open question; the fake
      // models the protocol's promise so the recovery logic can be tested.
      if (!this.cancelIsIgnored) {
        this._wedged = false;
        this._readsUntilWedge = this.wedgeAgainAfter ?? Infinity;
        // The camera abandons what it was about to say, so nothing stale is
        // left for the next request to collect.
        this._queue.length = 0;
        this._pendingSet = null;
      }
      this._busyFor = this.cancelLeavesBusyFor ?? 0;
    }
    return { bytesWritten: data ? data.length : 0, status: "ok" };
  }

  async controlTransferIn(setup, length) {
    this.calls.push(`controlTransferIn(0x${setup.request.toString(16)})`);
    const data = new DataView(new ArrayBuffer(4));
    data.setUint16(0, 4, true);
    // 0x2019 is Device Busy; anything else means ready.
    data.setUint16(2, this._busyFor-- > 0 ? 0x2019 : 0x2001, true);
    return { status: "ok", data };
  }

  // --- transfers ---------------------------------------------------------

  async transferOut(endpointNumber, data) {
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const type = view.getUint16(4, true);
    const code = view.getUint16(6, true);
    const txId = view.getUint32(8, true);
    this.sent.push({ endpointNumber, type, code, txId, bytes });

    if (this._stallOn.has(code)) {
      return { bytesWritten: 0, status: "stall" };
    }
    if (this.stallsOnCursorValue !== undefined && type === _PTP_DATA) {
      const value = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint16(12, true);
      if (
        code === _OC_SET_DEVICE_PROP_VALUE &&
        value === this.stallsOnCursorValue &&
        (this.stallsOnCursorTimes ?? Infinity) > (this._cursorStalls ?? 0)
      ) {
        this._cursorStalls = (this._cursorStalls ?? 0) + 1;
        // Accepted on the wire and never answered, and it stays that way until
        // the PTP stack is reset. A USB reopen does not clear it.
        this._stuckOnWrite = true;
        return { bytesWritten: bytes.length, status: "ok" };
      }
    }
    if (type === _PTP_COMMAND) {
      this._handleCommand(code, txId, bytes);
    } else if (type === _PTP_DATA) {
      this._handleData(code, txId, bytes.slice(12));
    }
    return { bytesWritten: bytes.length, status: "ok" };
  }

  async transferIn(endpointNumber, length) {
    if (this._stuckOnWrite) {
      return new Promise(() => {});
    }
    if (this._wedged || --this._readsUntilWedge < 0) {
      this._wedged = true;
      // Never resolves, and is never cancelled: exactly what the browser does
      // with an abandoned transfer.
      return new Promise(() => {});
    }
    if (this._failTransferInTimes > 0) {
      this._failTransferInTimes -= 1;
      throw Object.assign(new Error("transfer failed"), { name: "NetworkError" });
    }
    if (this._hangPending) {
      // Never resolves, which is the whole point: WebUSB gives no timeout and
      // a pending transfer cannot be cancelled.
      return new Promise(() => {});
    }
    if (this._stallPending) {
      this._stallPending = false;
      return { status: "stall", data: new DataView(new ArrayBuffer(0)) };
    }
    const next = this._queue.shift();
    if (!next) {
      throw new Error("FakeUSBDevice: transferIn with nothing queued");
    }
    return {
      status: "ok",
      data: new DataView(next.buffer, next.byteOffset, next.byteLength),
    };
  }

  // --- camera behaviour --------------------------------------------------

  _handleCommand(code, txId, bytes) {
    if (this._hangOn.has(code)) {
      this._hangPending = true;
      return;
    }
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const param = bytes.length >= 16 ? view.getUint32(12, true) : undefined;

    if (code === _OC_OPEN_SESSION) {
      this._queue.push(container(_PTP_RESPONSE, this._openSessionRc, txId));
      return;
    }
    if (code === _OC_CLOSE_SESSION) {
      this._queue.push(container(_PTP_RESPONSE, _RC_OK, txId));
      return;
    }
    if (code === _OC_GET_DEVICE_INFO) {
      // The recorded payload carries the transaction id it was captured with.
      // Replaying it verbatim makes the mismatch check fire on test data, so
      // restamp it with the id actually in flight.
      const info = this._deviceInfo.slice();
      new DataView(info.buffer).setUint32(8, txId, true);
      this._queue.push(info);
      this._queue.push(container(_PTP_RESPONSE, _RC_OK, txId));
      return;
    }
    if (code === _OC_GET_DEVICE_PROP_VALUE) {
      if (this._noDataPhaseOn.has(param) && this._noDataPhaseLeft > 0) {
        this._noDataPhaseLeft -= 1;
        // The camera answers with a response where a data container belongs.
        // One container only. The camera acknowledged the read and sent no
        // value; there is nothing further on the wire.
        this._queue.push(container(_PTP_RESPONSE, this._noDataPhaseRc, txId));
        return;
      }
      this._queue.push(this._propertyData(param, txId));
      this._queue.push(container(_PTP_RESPONSE, _RC_OK, txId));
      return;
    }
    if (code === _OC_SET_DEVICE_PROP_VALUE) {
      // The response waits for the data container that follows.
      this._pendingSet = { code: param, txId };
    }
  }

  _handleData(code, txId, payload) {
    if (code !== _OC_SET_DEVICE_PROP_VALUE || !this._pendingSet) return;
    const { code: propCode } = this._pendingSet;
    const rc = this._setRejectionCodes[propCode] ?? _RC_OK;
    if (rc === _RC_OK) this._storeWrite(propCode, payload);
    this._queue.push(container(_PTP_RESPONSE, rc, txId));
    this._pendingSet = null;
  }

  _storeWrite(code, payload) {
    if (payload.length === 0) return;
    const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
    if (payload.length >= 4) {
      this._intValues[code] = view.getInt32(0, true);
    } else if (payload.length >= 2) {
      this._intValues[code] = view.getUint16(0, true);
    }
  }

  _propertyData(code, txId) {
    if (code in this._stringValues) {
      return container(
        _PTP_DATA,
        _OC_GET_DEVICE_PROP_VALUE,
        txId,
        _encodePtpString(this._stringValues[code])
      );
    }
    const value = code in this._intValues ? this._intValues[code] : 0;
    return container(_PTP_DATA, _OC_GET_DEVICE_PROP_VALUE, txId, int32Payload(value));
  }

  /**
   * Fail the next `count` reads with a transport error, then behave.
   *
   * Called after connect() so the failures land on the operation under test
   * rather than being eaten by the session handshake.
   *
   * @param {number} count
   */
  failNextReads(count) {
    this._failTransferInTimes = count;
  }

  // --- assertions helpers -------------------------------------------------

  /** Operation codes of the command containers written, in order. */
  sentCommandCodes() {
    return this.sent.filter((s) => s.type === _PTP_COMMAND).map((s) => s.code);
  }
}
