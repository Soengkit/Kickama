module System.Random
  ( randomRIO
  ) where

randomRIO :: (Int, Int) -> IO Int
randomRIO (lo, _) = pure lo
