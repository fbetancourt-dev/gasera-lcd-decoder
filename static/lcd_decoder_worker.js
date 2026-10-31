/* ST7565 trace preprocessor. Runs outside the UI thread. */
'use strict';

function parseTraceSource(source) {
  const trimmed = source.trim();
  if (trimmed.startsWith('{')) return JSON.parse(trimmed);
  return Function(`"use strict";\n${source}\nreturn LCD_TRACE;`)();
}

function processTrace(trace, sourceName) {
  if (!trace || !Array.isArray(trace.events)) {
    throw new Error('The selected file does not contain an LCD_TRACE events array.');
  }

  const events = trace.events;
  const count = events.length;
  if (!count) throw new Error('The selected trace contains no events.');
  const controllerWidth = trace.width || 132;
  const pages = Math.ceil((trace.height || 64) / 8);
  const frameSize = controllerWidth * pages;
  const eventSegmentSize = 65536;
  const segmentCount = Math.ceil(count / eventSegmentSize);
  const checkpointStride = 2048;
  const checkpointCount = Math.ceil(count / checkpointStride);

  const segments = Array.from({ length: segmentCount }, (_, segmentIndex) => {
    const length = Math.min(eventSegmentSize, count - segmentIndex * eventSegmentSize);
    return {
      samples: new Uint32Array(length),
      values: new Uint8Array(length),
      flags: new Uint8Array(length),
      pages: new Uint8Array(length),
      columns: new Uint8Array(length),
      labels: new Uint8Array(length),
    };
  });
  const dataList = [];
  const commandList = [];
  const changeList = [];
  const checkpoints = new Uint8Array(checkpointCount * frameSize);
  const framebuffer = new Uint8Array(frameSize);

  for (let index = 0; index < count; index++) {
    const event = events[index];
    const segment = segments[Math.floor(index / eventSegmentSize)];
    const segmentOffset = index % eventSegmentSize;
    const sample = event[0] >>> 0;
    const isData = event[1] === 1;
    const value = event[2] & 0xff;
    const page = event[3] & 0xff;
    const column = event[4] & 0xff;
    const label = event[5] || '';

    segment.samples[segmentOffset] = sample;
    segment.values[segmentOffset] = value;
    segment.flags[segmentOffset] = isData ? 1 : 0;
    segment.pages[segmentOffset] = page;
    segment.columns[segmentOffset] = column;
    segment.labels[segmentOffset] =
      label === 'Set page' ? 1 :
      label === 'Set column high' ? 2 :
      label === 'Set column low' ? 3 :
      label === 'Data' ? 4 : 0;

    if (isData) {
      dataList.push(index);
      if (page < pages && column < controllerWidth) {
        const offset = page * controllerWidth + column;
        if (framebuffer[offset] !== value) changeList.push(index);
        framebuffer[offset] = value;
      }
    } else {
      commandList.push(index);
      if (value === 0xe2) framebuffer.fill(0);
    }

    if ((index + 1) % checkpointStride === 0 || index === count - 1) {
      const checkpoint = Math.floor(index / checkpointStride);
      checkpoints.set(framebuffer, checkpoint * frameSize);
    }

    if ((index + 1) % eventSegmentSize === 0 || index === count - 1) {
      postMessage({
        type: 'progress',
        phase: 'indexing',
        completed: index + 1,
        total: count,
        percent: Math.round(((index + 1) / count) * 100),
      });
    }
  }

  const dataIndices = Uint32Array.from(dataList);
  const commandIndices = Uint32Array.from(commandList);
  const changeIndices = Uint32Array.from(changeList);
  const payload = {
    type: 'ready',
    meta: {
      capture: trace.capture || sourceName || 'Selected trace',
      sampleRate: trace.sampleRate,
      controllerWidth,
      height: trace.height || 64,
      count,
      eventSegmentSize,
      segmentCount,
      checkpointStride,
      frameSize,
      channels: trace.channels,
      summary: trace.summary,
    },
    segments,
    dataIndices,
    commandIndices,
    changeIndices,
    checkpoints,
  };

  const transfer = [
    dataIndices.buffer,
    commandIndices.buffer,
    changeIndices.buffer,
    checkpoints.buffer,
  ];
  for (const segment of segments) {
    transfer.push(
      segment.samples.buffer,
      segment.values.buffer,
      segment.flags.buffer,
      segment.pages.buffer,
      segment.columns.buffer,
      segment.labels.buffer,
    );
  }
  postMessage(payload, transfer);
}

self.onmessage = ({ data }) => {
  try {
    let trace;
    let sourceName = data.name;
    if (data.type === 'load-url') {
      importScripts(data.url);
      trace = LCD_TRACE;
      sourceName = data.url;
    } else if (data.type === 'load-source') {
      trace = parseTraceSource(data.source);
    } else {
      throw new Error('Unknown trace loading request.');
    }
    processTrace(trace, sourceName);
  } catch (error) {
    postMessage({
      type: 'error',
      message: error && error.message ? error.message : String(error),
    });
  }
};
