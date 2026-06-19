module Data.Aeson.Key
  ( Key
  , toText
  ) where

import Data.Text (Text)

type Key = Text

toText :: Key -> Text
toText = id
