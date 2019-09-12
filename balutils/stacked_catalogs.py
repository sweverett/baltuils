from abc import ABCMeta, abstractmethod
import os
import fitsio
import h5py
import numpy as np
from astropy.table import Table, vstack, join
import matplotlib.pyplot as plt

# NOTE: Try using generators for Table chunks if files get too large!
# http://docs.astropy.org/en/stable/io/ascii/read.html#reading-large-tables-in-chunks

# NOTE: Could also switch to pandas DF as base catalog type, though I'm not sure
# matters much if we're careful about what we load into memory in the first place
# (i.e. using `cols`)

# NOTE: `Catalog` should relaly be an abstract class, but something in how
# I'm using ABCMeta is causing problems. Can fix later if we care
# class Catalog(ABCMeta):
class Catalog(object):

    def __init__(self, filename, cols=None):
        self.filename = filename
        self.cols = cols

        self._load_catalog()

        return

    # @abstractmethod
    def _load_catalog(self):
        pass

    @staticmethod
    def flux2mag(flux, zp=30.):
        return -2.5 * np.log10(flux) + zp

    def apply_cut(self, cut):
        self._cat = self._cat[cut]
        self.Nobjs = len(self._cat)

        return

    def get_cat(self):
        return self._cat

    def _check_for_cols(self, cols):
        for col in cols:
            if col not in self._cat.colnames:
                raise AttributeError('{} not found in joined '.format(col) +
                                     'catalog but required for requested cuts!')

        return

    # The following are so we can access the catalog
    # values similarly to a dict
    def __getitem__(self, key):
        return self._cat[key]

    def __setitem__(self, key, value):
        self._cat[key] = value

    def __delitem__(self, key):
        del self._cat[key]

    def __contains__(self, key):
        return key in self._cat

    def __len__(self):
        return len(self._cat)

    def __repr__(self):
        return repr(self._cat)

class GoldCatalog(Catalog):
    _gold_cut_cols_default = ['flags_foreground',
                              'flags_badregions',
                              'flags_footprint',
                              'meas_FLAGS_GOLD'
                              ]
    _gold_cut_cols_mof_only = ['flags_foreground',
                               'flags_badregions',
                               'flags_footprint',
                               'meas_FLAGS_GOLD_MOF_ONLY'
                               ]
    _gold_cut_cols_sof_only = ['flags_foreground',
                               'flags_badregions',
                               'flags_footprint',
                               'meas_FLAGS_GOLD_SOF_ONLY'
                               ]

    _gold_cut_cols = {'default':_gold_cut_cols_default,
                      'mof_only':_gold_cut_cols_mof_only,
                      'sof_only':_gold_cut_cols_sof_only
                      }

    def __init__(self, filename, cols=None, match_type='default'):
        super(GoldCatalog, self).__init__(filename, cols=None)
        return

    def _set_gold_colname(self, match_type)
        if match_type == 'default':
            self.flags_gold_colname = 'meas_FLAGS_GOLD'
        elif match_type == 'mof_only':
            self.flags_gold_colname = 'meas_FLAGS_GOLD_MOF_ONLY'
        elif match_type == 'sof_only':
            self.flags_gold_colname = 'meas_FLAGS_GOLD_SOF_ONLY'
        else:
            raise ValueError('match_type can only be default, mof_only, or sof_only')

        return

    def apply_gold_cuts(self):
        self._check_for_cols(self._gold_cut_cols[self.match_type])
        gold_cuts = np.where( (self._cat['flags_foreground'] == 0) &
                              (self._cat['flags_badregions'] < 2) &
                              (self._cat['flags_footprint'] == 1) &
                              (self._cat[self.flags_gold_colname] < 2)
                            )
        self.apply_cut(gold_cuts)

        return

    pass

class FitsCatalog(Catalog):
    def _load_catalog(self):
        self._cat = Table(fitsio.read(self.filename, columns=self.cols))
        self.Nobjs = len(self._cat)

        return

# TODO: Remove if not useful
class GoldFitsCatalog(FitsCatalog, GoldCatalog):
    def __init__(self, filename, cols=None, match_type='default'):
        super(GoldFitsCatalog, self).__init__(filename, cols=cols, match_type='default')
        self.match_type = match_type

        return

class DetectionCatalog(FitsCatalog, GoldCatalog):

    def __init__(self, filename, cols=None, match_type='default'):
        super(DetectionCatalog, self).__init__(filename, cols=cols, match_type='default')
        self.match_type = match_type

        self._check_for_duplicates()

        return

    def _check_for_duplicates(self):
        '''
        Balrog stack versions 1.4 and below have a small bug that
        seems to duplicate exactly 1 object, so check for these

        NOTE: Only works if there are exactly 1 extra duplicate for
        a given bal_id!
        '''
        unq, unq_idx, unq_cnt = np.unique(self._cat['bal_id'],
                                          return_inverse=True,
                                          return_counts=True)
        Nunq = len(unq)
        if Nunq != self.Nobjs:
            Ndups = self.Nobjs - Nunq
            dup_ids = unq[np.where(unq_cnt > 1)]
            print('Warning: Detection catalog has {} duplicate(s)!'.format(Ndups))
            print('Removing the following duplicates from detection catalog:')
            print(dup_ids)

            Nbefore = self.Nobjs
            for did in dup_ids:
                indx = np.where(self._cat['bal_id']==did)[0]
                self._cat.remove_row(indx[0])

            self.Nobjs = len(self._cat)
            assert self.Nobjs == (Nbefore - Ndups)

            print('{} duplicates removed, catalog size now {}'.format(Ndups, self.Nobjs))

        return

class H5Catalog(Catalog):

    def __init__(self, filename, basepath, cols=None):
        self.basepath = basepath
        super(H5Catalog, self).__init__(filename, cols=cols)

        return

    def _load_catalog(self):
        self._h5cat = h5py.File(self.filename)
        self._cat = Table()

        if self.cols is not None:
            for col in self.cols:
                path = os.path.join(self.basepath, col)
                self._cat[col] = self._h5cat[path][:]

        self.Nobjs = len(self._cat)

        return

    def add_col(self, col):
        path = os.path.join(self.basepath, col)
        self._cat[col] = self._h5cat[path]

        return

    def delete_col(self, col):
        self._cat.remove_column(col)

        return

    def __delete__(self):
        self._h5cat.close()
        super(Catalog, self).__delete__()

        return

class McalCatalog(H5Catalog):

    _shape_cut_cols = ['flags',
                       'T',
                       'psf_T',
                       'snr'
                      ]

    def __init__(self, filename, basepath, cols=None):
        super(McalCatalog, self).__init__(filename, basepath, cols=cols)

        self.calc_mags()

        return

    def calc_mags(self):
        '''
        Mcal catalogs don't automatically come with magnitudes
        '''

        fluxes = [c for c in self._cat.colnames if 'flux' in c.lower()]
        bands = [f[-1] for f in fluxes]

        for b in bands:
            self._cat['mag_{}'.format(b)]= self.flux2mag(self._cat['flux_{}'.format(b)])

        return

    def apply_shape_cuts(self):
        self._check_for_cols(self._shape_cut_cols)
        shape_cuts = np.where( (self._cat['flags'] == 0) &
                              ((self._cat['T']/self._cat['psf_T']) > 0.5) &
                              (self._cat['snr'] > 10) &
                              (self._cat['snr'] < 100)
                            )
        self.apply_cut(shape_cuts)

        return

class BalrogMcalCatalog(GoldCatalog):

    def __init__(self, mcal_file, det_file, mcal_cols=None, det_cols=None,
                 mcal_path='catalog/unsheared', match_type='default', save_all=False,
                 vb=False):

        self.mcal_file = mcal_file
        self.det_file = det_file
        self.mcal_cols = mcal_cols
        self.det_cols = det_cols
        self.mcal_path = mcal_path
        self.match_type = match_type
        self.save_all = save_all
        self.vb = vb

        self._set_gold_colname(match_type)

        self._load_catalog()

        return

    def _load_catalog(self):
        if self.vb is True: print('Loading Mcal catalog...')
        mcal = McalCatalog(self.mcal_file, self.mcal_path, cols=self.mcal_cols)
        mcal.calc_mags()

        if self.vb is True: print('Loading Detection catalog...')
        det = DetectionCatalog(self.det_file, cols=self.det_cols)

        if self.vb is True: print('Joining catalogs...')
        self._join(mcal.get_cat(), det.get_cat())

        return


    def _join(self, mcal, det):
        self._cat = join(mcal, det, join_type='left')

        if self.save_all is True:
            self.mcal = mcal
            self.det = det
        else:
            self.mcal = None
            self.det = None

        return


