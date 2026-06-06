import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { Divider } from './Divider.js'
import { SlashMenu, type SlashCommand } from './SlashMenu.js'
import { useTheme } from '../state/theme.js'

export function Input({ onSubmit, onCommand, placeholder = '输入消息... (/cmd  !bash  $py)' }: {
  onSubmit: (text: string) => void
  onCommand?: (cmd: SlashCommand) => void
  placeholder?: string
}) {
  const theme = useTheme()
  const [value, setValue] = useState('')
  const showMenu = value.startsWith('/') && value.length <= 12
  useInput((input, key) => {
    if (showMenu && key.tab) {
      const cmd = { name: value, description: '' } as SlashCommand
      onCommand?.(cmd)
      setValue('')
      return
    }
    if (key.return && !key.shift) {
      if (value.trim()) {
        if (value.startsWith('/') && onCommand) {
          onCommand({ name: value, description: '' })
        } else {
          onSubmit(value)
        }
        setValue('')
      }
      return
    }
    if (key.backspace || key.delete) { setValue((v) => v.slice(0, -1)); return }
    if (input) setValue((v) => v + input)
  })
  return (
    <Box flexDirection="column">
      <Divider />
      <Box paddingX={1}>
        <Text color={theme.hint}>{'> '}</Text>
        <Text color={theme.body}>{value || placeholder}</Text>
      </Box>
      {showMenu && <SlashMenu query={value} onSelect={(c) => onCommand?.(c)} />}
    </Box>
  )
}
