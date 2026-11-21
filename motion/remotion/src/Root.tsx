import React from 'react';
import {Composition} from 'remotion';
import {ConexaoFamilia} from './ConexaoFamilia';

// Teste das skills de motion: vertical 1080x1920, 10 s a 30 quadros por segundo.
export const Root: React.FC = () => {
	return (
		<Composition
			id="ConexaoFamilia"
			component={ConexaoFamilia}
			durationInFrames={300}
			fps={30}
			width={1080}
			height={1920}
		/>
	);
};
