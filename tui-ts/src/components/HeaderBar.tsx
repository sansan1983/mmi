import React from 'react'
import { Box } from 'ink'
import { Divider } from './Divider.js'

export function HeaderBar({ model, locale }: { model: string; locale: string }) {
  return (
    <Box flexDirection="column">
      <Divider label={`MMI  ·  ${model}  ·  ${locale}`} />
    </Box>
  )
}
