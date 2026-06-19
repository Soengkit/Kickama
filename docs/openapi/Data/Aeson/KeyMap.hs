module Data.Aeson.KeyMap
  ( KeyMap
  , empty
  , keys
  , lookup
  , fromList
  ) where

import Prelude hiding (lookup)
import qualified Data.Map.Strict as M
import Data.Aeson.Key (Key)

type KeyMap v = M.Map Key v

empty :: KeyMap v
empty = M.empty

keys :: KeyMap v -> [Key]
keys = M.keys

lookup :: Key -> KeyMap v -> Maybe v
lookup = M.lookup

fromList :: [(Key, v)] -> KeyMap v
fromList = M.fromList
