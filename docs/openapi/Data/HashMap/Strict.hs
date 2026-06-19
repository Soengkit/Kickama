module Data.HashMap.Strict
  ( HashMap
  , empty
  , null
  , keys
  , elems
  , toList
  , fromList
  , lookup
  ) where

import Prelude hiding (lookup, null)
import qualified Data.Map.Strict as M

newtype HashMap k v = HashMap (M.Map k v)
  deriving (Show, Eq)

empty :: HashMap k v
empty = HashMap M.empty

null :: HashMap k v -> Bool
null (HashMap m) = M.null m

keys :: HashMap k v -> [k]
keys (HashMap m) = M.keys m

elems :: HashMap k v -> [v]
elems (HashMap m) = M.elems m

toList :: HashMap k v -> [(k, v)]
toList (HashMap m) = M.toList m

fromList :: Ord k => [(k, v)] -> HashMap k v
fromList = HashMap . M.fromList

lookup :: Ord k => k -> HashMap k v -> Maybe v
lookup k (HashMap m) = M.lookup k m
