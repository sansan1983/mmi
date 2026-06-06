import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { Divider } from './Divider.js'
import { useTheme } from '../state/theme.js'

export function Input({ onSubmit, placeholder = '输入消息... (/cmd  !bash  $py)' }: {
  onSubmit: (text: string) => void
  placeholder?: string
}) {
  const theme = useTheme()
  const [value, setValue] = useState('')
  useInput((input, key) => {
    if (key.return && !key.shift) {
      if (value.trim()) {
        onSubmit(value)
        setValue('')
      }
      return
    }
    if (key.backspace || key.delete) {
      setValue((v) => v.slice(0, -1))
      return
    }
    if (input) setValue((v) => v + input)
  })
  return (
    <Box flexDirection="column">
      <Divider />
      <Box paddingX={1}>
        <Text color={theme.hint}>{value ? '> ' : '> '}</Text>
        <Text color={theme.body}>{value || placeholder}</Text>
      </Box>
    </Box>
  )
}
