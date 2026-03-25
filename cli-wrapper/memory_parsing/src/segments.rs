use eyre::Result;
use itertools::Itertools;

#[derive(Clone)]
pub struct Segment {
    range: std::ops::Range<usize>,
    bytes: Vec<u8>,
}

impl Segment {
    pub fn new(offset: usize, bytes: Vec<u8>) -> Self {
        let len = bytes.len();
        Self {
            bytes,
            range: std::ops::Range {
                start: offset,
                end: offset + len,
            },
        }
    }
    pub fn range(&self) -> &std::ops::Range<usize> {
        &self.range
    }
    pub fn get(&self, pointer: usize) -> Option<&[u8]> {
        if self.range.contains(&pointer) {
            Some(&self.bytes[(pointer - self.range.start)..])
        } else {
            None
        }
    }
    pub fn get_mut(&mut self, pointer: usize) -> Option<&mut [u8]> {
        if self.range.contains(&pointer) {
            Some(&mut self.bytes[(pointer - self.range.start)..])
        } else {
            None
        }
    }
    pub fn alloc(&mut self, size: usize) -> Option<usize> {
        let old_size = self.bytes.len();
        self.bytes.reserve(old_size + size);
        let pointer = self.range.start + old_size;
        self.bytes.extend(vec![0; size]);
        self.range.end += size;
        Some(pointer)
    }
    pub fn overlaps(&self, other: &Self) -> bool {
        (self.range.start <= other.range.start && other.range.start < self.range.end)
            || (other.range.start <= self.range.start && self.range.start < other.range.end)
    }
}

impl std::fmt::Debug for Segment {
    fn fmt(&self, fmt: &mut std::fmt::Formatter) -> std::fmt::Result {
        (self.range.start..).zip(self.bytes.iter()).try_for_each(
            |(offset, byte)| -> std::fmt::Result {
                if offset % 0x10 == 0 {
                    write!(fmt, "\n{offset:08x}: ")
                } else if offset % 0x2 == 0 {
                    write!(fmt, " ")
                } else {
                    Ok(())
                }
                .and_then(|_| write!(fmt, "{byte:02x}"))
            },
        )
    }
}

impl std::cmp::PartialEq for Segment {
    fn eq(&self, other: &Self) -> bool {
        self.range == other.range
    }
}

impl std::cmp::PartialOrd for Segment {
    fn partial_cmp(&self, other: &Segment) -> Option<std::cmp::Ordering> {
        if self.range.end <= other.range.start {
            Some(std::cmp::Ordering::Less)
        } else if other.range.end <= other.range.start {
            Some(std::cmp::Ordering::Greater)
        } else if self.range == other.range {
            Some(std::cmp::Ordering::Equal)
        } else {
            None
        }
    }
}

#[derive(Clone)]
pub struct Segments {
    segments: Vec<Segment>,
}

impl Segments {
    pub fn single(offset: usize, bytes: Vec<u8>) -> Self {
        Self {
            segments: vec![Segment::new(offset, bytes)],
        }
    }
    pub fn from_segment(segment: Segment) -> Self {
        Self {
            segments: vec![segment],
        }
    }
    pub fn new(mut segments: Vec<Segment>) -> Result<Self> {
        // Even if the segments overlap, the comparison will still be total.
        // We will detect overlaps after sorting.
        segments.sort_by(|s0, s1| s0.partial_cmp(s1).unwrap_or(std::cmp::Ordering::Equal));
        match segments
            .iter()
            .combinations(2)
            .find(|vec| vec[0].overlaps(vec[1]))
        {
            Some(vec) => Err(eyre::eyre!(
                "0x{:08x}--0x{:08x} overlaps 0x{:08x}--0x{:08x}",
                vec[0].range.start,
                vec[0].range.end,
                vec[1].range.start,
                vec[1].range.end
            )),
            None => Ok(Self { segments }),
        }
    }
    fn idx(&self, pointer: usize) -> Option<usize> {
        self.segments
            .binary_search_by(|segment| {
                if pointer < segment.range.start {
                    std::cmp::Ordering::Greater
                } else if pointer < segment.range.end {
                    std::cmp::Ordering::Equal
                } else {
                    std::cmp::Ordering::Less
                }
            })
            .ok()
    }
    pub fn get(&self, pointer: usize) -> Option<&[u8]> {
        let idx = self.idx(pointer)?;
        self.segments[idx].get(pointer)
    }
    pub fn get_mut(&mut self, pointer: usize) -> Option<&mut [u8]> {
        let idx = self.idx(pointer)?;
        self.segments[idx].get_mut(pointer)
    }
    pub fn alloc(&mut self, length: usize) -> Option<usize> {
        let last = self.segments.len() - 1;
        self.segments[last].alloc(length)
    }
    pub fn iter(&self) -> std::slice::Iter<'_, Segment> {
        self.segments.iter()
    }
    pub fn extend(&self, other: &Self) -> Result<Self> {
        Self::new(
            [self.segments.clone(), other.segments.clone()]
                .into_iter()
                .concat(),
        )
    }
}

impl std::fmt::Debug for Segments {
    fn fmt(&self, fmt: &mut std::fmt::Formatter) -> std::fmt::Result {
        self.segments
            .iter()
            .try_for_each(|segment| writeln!(fmt, "{segment:?}"))
    }
}
