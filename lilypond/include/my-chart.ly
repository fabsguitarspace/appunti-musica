\layout {
  \context {
    \Score
    \omit Staff.TimeSignature
    \remove "Bar_number_engraver"
  }
  \context {
      \Staff
      \override VerticalAxisGroup.default-staff-staff-spacing =
        #'((basic-distance . 14)
           (minimum-distance . 12)
           (padding . 6)
           (stretchability . 0))
    }
  \context {
    \ChordNames
    chordChanges = ##t
  }
}
